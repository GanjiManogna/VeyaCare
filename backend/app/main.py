
import asyncio
import logging

from datetime import date, timedelta

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequestHandler,
    SmallWebRTCRequest,
    SmallWebRTCPatchRequest,
)

from app.database import Base, engine, get_db, SessionLocal
from app.models import Doctor, TimeSlot, Appointment
from app.schemas import (
    AvailabilityRequest,
    BookingRequest,
    CancellationRequest,
)
from app.tools import (
    check_doctor_availability,
    book_appointment,
    cancel_appointment,
)
from app.phone_validation import is_valid_indian_mobile
from app.voice.bot import create_voice_pipeline, normalize_display_name
from app.visit_reasons import VISIT_REASONS
from app.health_concerns import HEALTH_CONCERNS


logger = logging.getLogger(__name__)

app = FastAPI(
    title="VeyaCare",
    description="Voice-powered doctor appointment booking system",
    version="1.0.0",
)

DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)

# WebRTC connection manager
webrtc_handler = SmallWebRTCRequestHandler()

# Keep references to active voice pipeline tasks.
voice_tasks = set()


def _display_name_from_request_data(request_data):
    """Read a short display label from the WebRTC offer's custom payload."""
    if not isinstance(request_data, dict):
        return ""
    value = request_data.get("display_name")
    if not isinstance(value, str):
        return ""
    # Remove control characters and bound caller-provided text before adding it
    # as data to the assistant context. Never log this value.
    return normalize_display_name(value)


async def run_voice_pipeline(connection, display_name=""):
    """Run a voice pipeline for one browser connection."""

    try:
        await create_voice_pipeline(connection, display_name=display_name)
    except Exception:
        logger.exception(
            "Voice pipeline failed for connection %s",
            connection.pc_id,
        )


async def on_webrtc_connection(connection, display_name=""):
    """Start the voice pipeline without blocking the SDP response."""

    task = asyncio.create_task(run_voice_pipeline(connection, display_name))
    voice_tasks.add(task)
    task.add_done_callback(voice_tasks.discard)


def initialize_database():
    """Apply additive columns and idempotently seed clinic catalogue/slots."""

    Base.metadata.create_all(bind=engine)

    # SQLite does not apply newly added SQLAlchemy columns to existing tables.
    # These additive migrations preserve all existing doctor and appointment rows.
    with engine.begin() as connection:
        doctor_columns = {row["name"] for row in connection.execute(text("PRAGMA table_info(doctors)")).mappings()}
        appointment_columns = {row["name"] for row in connection.execute(text("PRAGMA table_info(appointments)")).mappings()}
        if "consultation_fee" not in doctor_columns:
            connection.execute(text("ALTER TABLE doctors ADD COLUMN consultation_fee INTEGER NOT NULL DEFAULT 500"))
        if "booked_by_name" not in appointment_columns:
            connection.execute(text("ALTER TABLE appointments ADD COLUMN booked_by_name VARCHAR"))
        for column_name, column_type in (
            ("visit_reason", "VARCHAR"),
            ("visit_reason_details", "VARCHAR"),
            ("health_concern", "VARCHAR"),
            ("health_concern_details", "VARCHAR"),
            ("appointment_reference", "VARCHAR"),
            ("checkin_code", "VARCHAR"),
        ):
            if column_name not in appointment_columns:
                connection.execute(text(f"ALTER TABLE appointments ADD COLUMN {column_name} {column_type}"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_appointment_reference "
            "ON appointments (appointment_reference)"
        ))

    db = SessionLocal()

    try:
        catalogue = [
            ("Dr. Ananya Rao", "Cardiology", 12, 750),
            ("Dr. Kabir Menon", "Cardiology", 9, 700),
            ("Dr. Rahul Sharma", "Dermatology", 8, 650),
            ("Dr. Meera Iyer", "Dermatology", 11, 700),
            ("Dr. Priya Reddy", "General Medicine", 10, 500),
            ("Dr. Nikhil Desai", "General Medicine", 7, 450),
            ("Dr. Arjun Mehta", "Orthopedics", 15, 800),
            ("Dr. Sana Kapoor", "Orthopedics", 9, 700),
            ("Dr. Ishita Banerjee", "Neurology", 13, 900),
            ("Dr. Vivek Nair", "Neurology", 8, 800),
            ("Dr. Aditi Kulkarni", "Pediatrics", 10, 650),
            ("Dr. Rohan Chatterjee", "Pediatrics", 6, 550),
            ("Dr. Kavya Srinivasan", "Gynecology", 14, 850),
            ("Dr. Neha Bhat", "Gynecology", 8, 700),
            ("Dr. Farhan Ali", "ENT", 11, 650),
            ("Dr. Leena Joseph", "ENT", 7, 550),
            ("Dr. Pooja Shah", "Ophthalmology", 12, 700),
            ("Dr. Aditya Bose", "Ophthalmology", 6, 550),
            ("Dr. Ritu Malhotra", "Dentistry", 10, 600),
            ("Dr. Sameer Kulkarni", "Dentistry", 7, 500),
        ]
        doctor_index = {(doctor.name, doctor.speciality): doctor for doctor in db.query(Doctor).all()}
        for name, speciality, experience, fee in catalogue:
            doctor = doctor_index.get((name, speciality))
            if doctor is None:
                doctor = Doctor(name=name, speciality=speciality, experience=experience, consultation_fee=fee)
                db.add(doctor)
                db.flush()
                doctor_index[(name, speciality)] = doctor

            times = ["09:00 AM", "10:00 AM", "11:30 AM", "02:00 PM"]
            existing_slots = {
                (slot_date, slot_time)
                for slot_date, slot_time in db.query(TimeSlot.date, TimeSlot.time).filter_by(doctor_id=doctor.id).all()
            }
            for day_offset in range(1, 6):
                appointment_date = (date.today() + timedelta(days=day_offset)).isoformat()
                for time in times:
                    if (appointment_date, time) not in existing_slots:
                        db.add(TimeSlot(doctor_id=doctor.id, date=appointment_date, time=time, status="available"))
        db.commit()

    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    initialize_database()


@app.get("/")
def home():
    return {
        "message": "VeyaCare is running."
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "VeyaCare",
    }


# --------------------------------------------------
# WebRTC voice connection endpoints
# --------------------------------------------------

@app.post("/api/offer")
async def handle_offer(request: SmallWebRTCRequest):
    """Create or update a browser WebRTC voice connection."""

    display_name = _display_name_from_request_data(request.request_data)

    async def start_session(connection):
        # The callback runs only when Pipecat creates a new PC. Renegotiations
        # reuse the original session and cannot trigger a second greeting.
        await on_webrtc_connection(connection, display_name)

    answer = await webrtc_handler.handle_web_request(
        request,
        start_session,
    )

    if answer is None:
        raise HTTPException(
            status_code=500,
            detail="Could not create WebRTC connection.",
        )

    return answer


@app.patch("/api/offer")
async def handle_ice_candidates(
    request: SmallWebRTCPatchRequest,
):
    """Exchange ICE candidates for the browser voice connection."""

    await webrtc_handler.handle_patch_request(request)

    return {"status": "success"}


# --------------------------------------------------
# Existing doctor and appointment API endpoints
# --------------------------------------------------

@app.get("/api/doctors")
def get_doctors(db: Session = Depends(get_db)):
    doctors = db.query(Doctor).all()

    return [
        {
            "id": doctor.id,
            "name": doctor.name,
            "speciality": doctor.speciality,
            "experience": doctor.experience,
            "consultation_fee": doctor.consultation_fee,
        }
        for doctor in doctors
    ]


@app.get("/api/visit-reasons")
def get_visit_reasons():
    return VISIT_REASONS


@app.get("/api/health-concerns")
def get_health_concerns():
    return HEALTH_CONCERNS


@app.get("/api/availability")
def get_availability(
    speciality: str | None = None,
    date: str | None = None,
    db: Session = Depends(get_db),
):
    return check_doctor_availability(db, speciality, date)


@app.post("/api/appointments")
def create_appointment(
    request: BookingRequest,
    db: Session = Depends(get_db),
):
    result = book_appointment(
        db=db,
        phone_number=request.phone_number,
        doctor_id=request.doctor_id,
        slot_id=request.slot_id,
        patient_name=request.patient_name,
        booked_by_name=request.booked_by_name,
        visit_reason=request.visit_reason,
        visit_reason_details=request.visit_reason_details,
        health_concern=request.health_concern,
        health_concern_details=request.health_concern_details,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=409,
            detail=result if result.get("code") else result["message"],
        )

    return result


@app.post("/api/appointments/cancel")
def remove_appointment(
    request: CancellationRequest,
    db: Session = Depends(get_db),
):
    result = cancel_appointment(
        db=db,
        phone_number=request.phone_number,
        appointment_id=request.appointment_id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=404,
            detail=result["message"],
        )

    return result


@app.get("/api/appointments")
def get_appointments(
    phone_number: str = Query(..., min_length=10, max_length=10, pattern=r"^[6-9][0-9]{9}$"),
    db: Session = Depends(get_db),
):
    if not is_valid_indian_mobile(phone_number):
        raise HTTPException(status_code=422, detail="Enter a valid 10-digit Indian mobile number.")

    query = db.query(Appointment).filter(Appointment.phone_number == phone_number)

    appointments = query.order_by(
        Appointment.id.desc()
    ).all()

    return [
        {
            "id": appointment.id,
            "patient_name": appointment.patient_name,
            "booked_by_name": appointment.booked_by_name,
            "doctor": appointment.doctor.name,
            "speciality": appointment.doctor.speciality,
            "date": appointment.slot.date,
            "time": appointment.slot.time,
            "status": appointment.status,
            "visit_reason": appointment.visit_reason,
            "visit_reason_details": appointment.visit_reason_details,
            "health_concern": appointment.health_concern,
            "health_concern_details": appointment.health_concern_details,
            "appointment_reference": appointment.appointment_reference,
            "checkin_code": appointment.checkin_code,
            "consultation_fee": appointment.doctor.consultation_fee,
        }
        for appointment in appointments
    ]
