
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
import secrets

from app.models import Doctor, TimeSlot, Appointment
from app.phone_validation import is_valid_indian_mobile
from app.visit_reasons import visit_reasons_for
from app.health_concerns import HEALTH_CONCERNS, is_emergency_warning


def _new_appointment_reference(db):
    india = timezone(timedelta(hours=5, minutes=30))
    prefix = datetime.now(india).strftime("VY-%y%m-")
    for _ in range(100):
        reference = f"{prefix}{secrets.randbelow(100000):05d}"
        if not db.query(Appointment.id).filter(Appointment.appointment_reference == reference).first():
            return reference
    raise RuntimeError("Unable to allocate a unique appointment reference")


def check_doctor_availability(
    db: Session,
    speciality: str | None = None,
    date: str | None = None,
):
    """Return slots not occupied by an active booked appointment.

    The slot status is a reservation hint; active appointment rows are the
    source of truth for whether a slot is occupied. This also makes a stale
    ``booked`` slot flag visible and bookable when no active booking exists.
    """

    query = db.query(Doctor)

    if speciality:
        query = query.filter(
            Doctor.speciality.ilike(f"%{speciality}%")
        )

    doctors = query.all()
    results = []

    for doctor in doctors:
        active_booking = db.query(Appointment.id).filter(
            Appointment.slot_id == TimeSlot.id,
            Appointment.status == "booked",
        ).exists()
        slots_query = db.query(TimeSlot).filter(
            TimeSlot.doctor_id == doctor.id,
            TimeSlot.status.in_(("available", "booked")),
            ~active_booking,
        )

        if date:
            slots_query = slots_query.filter(TimeSlot.date == date)

        slots = slots_query.all()

        if slots:
            results.append({
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "speciality": doctor.speciality,
                "experience": doctor.experience,
                "consultation_fee": doctor.consultation_fee,
                "available_slots": [
                    {
                        "slot_id": slot.id,
                        "date": slot.date,
                        "time": slot.time,
                    }
                    for slot in slots
                ],
            })

    return results


def book_appointment(
    db: Session,
    phone_number: str,
    doctor_id: int,
    slot_id: int,
    patient_name: str | None = None,
    booked_by_name: str | None = None,
    visit_reason: str | None = None,
    visit_reason_details: str | None = None,
    health_concern: str | None = None,
    health_concern_details: str | None = None,
):
    """Book an available slot for a patient."""

    if not is_valid_indian_mobile(phone_number):
        return {"success": False, "message": "Please provide a valid 10-digit Indian mobile number."}
    if not isinstance(patient_name, str) or not patient_name.strip():
        return {"success": False, "message": "Please provide the patient's full name."}
    normalized_concern = " ".join(str(health_concern or "").split())
    normalized_concern_details = " ".join(str(health_concern_details or "").split()) or None
    if normalized_concern:
        if normalized_concern not in HEALTH_CONCERNS:
            return {"success": False, "message": "Choose a health concern from the clinic intake options."}
        if normalized_concern == "Other" and not normalized_concern_details:
            return {"success": False, "message": "Please briefly describe the concern selected as Other."}
        if is_emergency_warning(f"{normalized_concern} {normalized_concern_details or ''}"):
            return {"success": False, "code": "emergency_care", "message": "This concern may need urgent attention. Please contact emergency services or go to the nearest emergency department now instead of booking a routine appointment."}
        if len(normalized_concern_details or "") > 500:
            return {"success": False, "message": "Health concern details must be 500 characters or fewer."}

    # Serialize SQLite writers before reading existing appointments. This
    # makes the patient/date/time conflict check and slot reservation atomic.
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))

    slot = db.query(TimeSlot).filter(
        TimeSlot.id == slot_id,
        TimeSlot.doctor_id == doctor_id,
    ).first()

    if not slot:
        db.rollback()
        return {
            "success": False,
            "message": "Sorry, this appointment slot is no longer available.",
        }

    if normalized_concern:
        normalized_reason = normalized_concern
        normalized_details = normalized_concern_details
    else:
        valid_reasons = visit_reasons_for(slot.doctor.speciality)
        normalized_reason = " ".join(str(visit_reason or "").split())
        if normalized_reason not in valid_reasons:
            db.rollback()
            return {"success": False, "message": "Choose a visit reason from the options for this speciality."}
        normalized_details = " ".join(str(visit_reason_details or "").split()) or None
        if normalized_details and len(normalized_details) > 500:
            db.rollback()
            return {"success": False, "message": "Visit reason details must be 500 characters or fewer."}

    conflict = (
        db.query(Appointment, Doctor)
        .join(TimeSlot, Appointment.slot_id == TimeSlot.id)
        .join(Doctor, Appointment.doctor_id == Doctor.id)
        .filter(
            Appointment.phone_number == phone_number,
            Appointment.status == "booked",
            TimeSlot.date == slot.date,
            TimeSlot.time == slot.time,
        )
        .first()
    )
    if conflict:
        existing, existing_doctor = conflict
        db.rollback()
        return {
            "success": False,
            "code": "patient_time_conflict",
            "message": f"This patient already has a booked appointment with {existing_doctor.name} on {slot.date} at {slot.time}. Choose a different time.",
            "conflict": {
                "date": slot.date,
                "time": slot.time,
                "doctor": existing_doctor.name,
                "appointment_id": existing.id,
            },
        }

    active_slot_booking = db.query(Appointment.id).filter(
        Appointment.slot_id == slot_id,
        Appointment.status == "booked",
    ).first()
    if slot.status not in ("available", "booked") or active_slot_booking:
        db.rollback()
        return {
            "success": False,
            "message": "Sorry, this appointment slot is no longer available.",
        }

    # Reserve the slot only if it is still available.
    active_slot_booking_query = db.query(Appointment.id).filter(
        Appointment.slot_id == TimeSlot.id,
        Appointment.status == "booked",
    ).exists()
    updated = db.query(TimeSlot).filter(
        TimeSlot.id == slot_id,
        TimeSlot.status.in_(("available", "booked")),
        ~active_slot_booking_query,
    ).update(
        {"status": "booked"},
        synchronize_session=False,
    )

    if updated == 0:
        db.rollback()
        return {
            "success": False,
            "message": "This slot has already been booked.",
        }

    appointment = Appointment(
        patient_name=patient_name,
        booked_by_name=booked_by_name,
        phone_number=phone_number,
        doctor_id=doctor_id,
        slot_id=slot_id,
        status="booked",
        visit_reason=normalized_reason,
        visit_reason_details=normalized_details,
        health_concern=normalized_concern or normalized_reason,
        health_concern_details=normalized_concern_details or normalized_details,
        appointment_reference=_new_appointment_reference(db),
        checkin_code=f"{secrets.randbelow(900000) + 100000:06d}",
    )

    db.add(appointment)

    try:
        db.commit()
        db.refresh(appointment)
    except Exception:
        db.rollback()
        raise

    return {
        "success": True,
        "message": "Appointment booked successfully.",
        "appointment_id": appointment.id,
        "doctor": appointment.doctor.name,
        "date": slot.date,
        "time": slot.time,
        "patient_name": patient_name,
        "booked_by_name": booked_by_name,
        "consultation_fee": appointment.doctor.consultation_fee,
        "visit_reason": appointment.visit_reason,
        "visit_reason_details": appointment.visit_reason_details,
        "health_concern": appointment.health_concern,
        "health_concern_details": appointment.health_concern_details,
        "appointment_reference": appointment.appointment_reference,
        "checkin_code": appointment.checkin_code,
    }


def cancel_appointment(
    db: Session,
    phone_number: str,
    appointment_id: int,
):
    """Cancel an appointment after verifying the patient's phone number."""

    if not is_valid_indian_mobile(phone_number):
        return {"success": False, "message": "Please provide a valid 10-digit Indian mobile number."}

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.phone_number == phone_number,
        Appointment.status == "booked",
    ).first()

    if not appointment:
        return {
            "success": False,
            "message": "No active appointment found for those details.",
        }

    slot = db.query(TimeSlot).filter(
        TimeSlot.id == appointment.slot_id
    ).first()

    appointment.status = "cancelled"

    if slot:
        remaining_active = db.query(Appointment.id).filter(
            Appointment.slot_id == slot.id,
            Appointment.status == "booked",
            Appointment.id != appointment.id,
        ).first()
        if not remaining_active:
            slot.status = "available"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "success": True,
        "message": "Appointment cancelled successfully.",
        "appointment_id": appointment.id,
    }

