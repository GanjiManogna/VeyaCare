import unittest
from types import SimpleNamespace
from datetime import date
from datetime import datetime as real_datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Appointment, Doctor, TimeSlot
from app.tools import book_appointment as _book_appointment
from app.voice import appointment_tools as voice_tools
from app.voice import bot
from app.voice.appointment_tools import record_user_transcript
from app.voice.tool_schemas import APPOINTMENT_TOOLS
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.adapters.llm.services.gemini_adapter import GeminiLLMAdapter
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app import main
from app.schemas import BookingRequest, CancellationRequest
from app.phone_validation import is_valid_indian_mobile
from pipecat.frames.frames import (
    EndFrame, ErrorFrame, FunctionCallResultFrame, InterruptionFrame, LLMFullResponseEndFrame,
    LLMFullResponseStartFrame, LLMTextFrame, TTSStoppedFrame, TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection


class BackendSafetyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.original_session = voice_tools.SessionLocal
        voice_tools.SessionLocal = self.Session
        with self.Session() as db:
            doctor = Doctor(name="Dr. Test", speciality="Cardiology", experience=10)
            db.add(doctor)
            db.flush()
            slot = TimeSlot(doctor_id=doctor.id, date="2099-01-01", time="09:00 AM", status="available")
            db.add(slot)
            db.commit()
            self.doctor_id, self.slot_id = doctor.id, slot.id
        self.state = {
            "latest_user_text": "", "transcript_sequence": 0,
            "awaiting_confirmation": None, "confirmation_grant": None,
            "pending_phone": None, "confirmed_phone": None,
            "pending_booking": None, "pending_cancellation": None,
            "display_name": "Patient A", "booking_for": None, "patient_name": None,
        }

    def tearDown(self):
        voice_tools.SessionLocal = self.original_session
        self.engine.dispose()

    def call(self, handler, arguments):
        result = {}
        class Immediate:
            def __await__(self):
                if False: yield None
                return None
        def callback(value):
            result.update(value)
            return Immediate()
        params = SimpleNamespace(arguments=arguments, app_resources=self.state, result_callback=callback)
        coroutine = handler(params)
        with self.assertRaises(StopIteration):
            coroutine.send(None)
        return result

    def make_slot(self, doctor_name, speciality, time):
        with self.Session() as db:
            doctor = Doctor(name=doctor_name, speciality=speciality, experience=6, consultation_fee=600)
            db.add(doctor)
            db.flush()
            slot = TimeSlot(doctor_id=doctor.id, date="2099-01-01", time=time, status="available")
            db.add(slot)
            db.commit()
            return doctor.id, slot.id

    def book(self, *args, **kwargs):
        """Use an explicit valid reason in legacy booking-focused tests."""
        kwargs.setdefault("visit_reason", "Other")
        if len(args) < 5:
            kwargs.setdefault("patient_name", "Test Patient")
        return _book_appointment(*args, **kwargs)

    def prepare_self_booking(self):
        record_user_transcript(self.state, "I am booking for myself")
        self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        self.offer_test_slot()
        record_user_transcript(self.state, "My full name is Patient A")
        self.call(voice_tools.set_patient_name_handler, {"patient_name": "Patient A"})
        self.prepare_cardio_reason("Patient A")

    def offer_test_slot(self):
        record_user_transcript(self.state, "I want Cardiology on 2099-01-01")
        availability = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2099-01-01"})
        self.assertTrue(availability["success"])
        bot.capture_offered_slots(self.state, "Dr. Test, Cardiology, on January 1, 2099 at 09:00 AM")
        self.assertEqual(len(self.state["last_offered_slots"]), 1)
        record_user_transcript(self.state, "Yes")
        selected = self.call(voice_tools.select_appointment_slot_handler, {"doctor_id": self.doctor_id, "slot_id": self.slot_id})
        self.assertTrue(selected["success"])
        return selected

    def prepare_cardio_reason(self, patient_name):
        record_user_transcript(self.state, "Routine check-up")
        self.call(voice_tools.get_health_concerns_handler, {})
        self.call(voice_tools.set_health_concern_handler, {"visit_reason": "Routine check-up"})

    def submit_phone(self, phone):
        record_user_transcript(self.state, f"My mobile number is {phone}")
        return self.call(voice_tools.set_phone_handler, {})

    def test_indian_mobile_validation_and_invalid_voice_booking_block(self):
        for first_digit in "6789":
            self.assertTrue(is_valid_indian_mobile(first_digit + "123456789"))
        for invalid in (
            "912345678", "91234567890", "5123456789", "1123456789",
            "91234abc89", "+919123456789", " 9123456789", "９123456789",
        ):
            self.assertFalse(is_valid_indian_mobile(invalid), invalid)
            response = self.call(voice_tools.set_phone_handler, {"phone_number": invalid})
            self.assertFalse(response["success"])
            self.assertIsNone(self.state["pending_phone"])
            self.assertIsNone(self.state["confirmed_phone"])
            with self.Session() as db:
                result = self.book(db, invalid, self.doctor_id, self.slot_id)
                self.assertFalse(result["success"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_api_phone_schemas_reject_invalid_indian_mobile_numbers(self):
        for invalid in ("123456789", "91234567890", "5123456789", "91234ab890"):
            with self.assertRaises(Exception):
                BookingRequest(phone_number=invalid, doctor_id=1, slot_id=1)
            with self.assertRaises(Exception):
                CancellationRequest(phone_number=invalid, appointment_id=1)
        with self.assertRaises(Exception):
            BookingRequest(phone_number="9123456789", doctor_id=1, slot_id=1, patient_name="   ")
        with self.assertRaises(Exception):
            BookingRequest(phone_number="9123456789", doctor_id=1, slot_id=1, patient_name="Patient", visit_reason="Other")

    def test_same_patient_same_time_conflict_with_another_doctor_of_same_speciality(self):
        other_doctor, other_slot = self.make_slot("Dr. Heart", "Cardiology", "09:00 AM")
        with self.Session() as db:
            self.assertTrue(self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient")["success"])
            result = self.book(db, "9123456789", other_doctor, other_slot, "Patient")
            self.assertEqual(result["code"], "patient_time_conflict")

    def test_same_patient_cannot_book_same_time_across_doctors_and_specialities(self):
        other_doctor, other_slot = self.make_slot("Dr. Skin", "Dermatology", "09:00 AM")
        with self.Session() as db:
            first = self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient A")
            self.assertTrue(first["success"])
            with self.assertRaises(HTTPException) as error:
                main.create_appointment(
                    BookingRequest(phone_number="9123456789", doctor_id=other_doctor, slot_id=other_slot, patient_name="Patient A", visit_reason="Routine check-up", health_concern="Routine check-up"),
                    db,
                )
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(error.exception.detail["code"], "patient_time_conflict")
            self.assertEqual(error.exception.detail["conflict"]["doctor"], "Dr. Test")
            self.assertIn("already has a booked appointment", error.exception.detail["message"])
            self.assertEqual(db.query(Appointment).count(), 1)

    def test_different_patient_same_time_and_same_patient_different_time_are_allowed(self):
        same_time_doctor, same_time_slot = self.make_slot("Dr. Eye", "Ophthalmology", "09:00 AM")
        other_time_doctor, other_time_slot = self.make_slot("Dr. Neuro", "Neurology", "10:00 AM")
        with self.Session() as db:
            self.assertTrue(self.book(db, "9123456789", self.doctor_id, self.slot_id)["success"])
            other_patient = self.book(db, "8123456789", same_time_doctor, same_time_slot)
            self.assertTrue(other_patient["success"])
            different_time = self.book(db, "9123456789", other_time_doctor, other_time_slot)
            self.assertTrue(different_time["success"])
            self.assertEqual(db.query(Appointment).count(), 3)

    def test_cancelled_booking_no_longer_blocks_same_patient_time(self):
        with self.Session() as db:
            first = self.book(db, "9123456789", self.doctor_id, self.slot_id)
            self.assertTrue(first["success"])
            cancelled = main.remove_appointment(
                CancellationRequest(phone_number="9123456789", appointment_id=first["appointment_id"]), db
            )
            self.assertTrue(cancelled["success"])
            next_booking = self.book(db, "8123456789", self.doctor_id, self.slot_id)
            self.assertTrue(next_booking["success"])

    def test_active_booking_blocks_availability_but_cancellation_releases_it(self):
        with self.Session() as db:
            before = main.get_availability("Cardiology", "2099-01-01", db)
            self.assertIn(self.slot_id, [slot["slot_id"] for doctor in before for slot in doctor["available_slots"]])
            voice_before = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2099-01-01"})
            self.assertEqual(
                {slot["slot_id"] for doctor in before for slot in doctor["available_slots"]},
                {slot["slot_id"] for doctor in voice_before["doctors"] for slot in doctor["available_slots"]},
            )
            booked = self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient A")
            active = main.get_availability("Cardiology", "2099-01-01", db)
            self.assertNotIn(self.slot_id, [slot["slot_id"] for doctor in active for slot in doctor["available_slots"]])
            voice_active = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2099-01-01"})
            self.assertNotIn(self.slot_id, [slot["slot_id"] for doctor in voice_active["doctors"] for slot in doctor["available_slots"]])
            self.assertTrue(main.remove_appointment(CancellationRequest(phone_number="9123456789", appointment_id=booked["appointment_id"]), db)["success"])
            self.assertEqual(db.query(Appointment).filter_by(id=booked["appointment_id"]).one().status, "cancelled")
            released = main.get_availability("Cardiology", "2099-01-01", db)
            self.assertIn(self.slot_id, [slot["slot_id"] for doctor in released for slot in doctor["available_slots"]])
            voice_released = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2099-01-01"})
            self.assertIn(self.slot_id, [slot["slot_id"] for doctor in voice_released["doctors"] for slot in doctor["available_slots"]])
            different_patient = self.book(db, "8123456789", self.doctor_id, self.slot_id, "Patient B")
            self.assertTrue(different_patient["success"])

    def test_stale_booked_slot_flag_without_active_appointment_is_available(self):
        with self.Session() as db:
            db.query(TimeSlot).filter_by(id=self.slot_id).update({"status": "booked"})
            db.commit()
            available = main.get_availability("Cardiology", "2099-01-01", db)
            self.assertIn(self.slot_id, [slot["slot_id"] for doctor in available for slot in doctor["available_slots"]])
            result = self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient A")
            self.assertTrue(result["success"])

    def test_booking_for_someone_else_uses_patient_phone_and_keeps_booking_contact(self):
        payload = BookingRequest(
            phone_number="9123456789", doctor_id=self.doctor_id, slot_id=self.slot_id,
            patient_name="Aarav Patient", booked_by_name="Kiran Booker", visit_reason="Routine check-up", health_concern="Routine check-up",
        )
        with self.Session() as db:
            result = main.create_appointment(payload, db)
            self.assertTrue(result["success"])
            appointment = db.query(Appointment).filter_by(id=result["appointment_id"]).one()
            self.assertEqual(appointment.patient_name, "Aarav Patient")
            self.assertEqual(appointment.phone_number, "9123456789")
            self.assertEqual(appointment.booked_by_name, "Kiran Booker")

    def test_successful_booking_persists_reference_checkin_and_visit_reason(self):
        with self.Session() as db:
            result = self.book(
                db, "9123456789", self.doctor_id, self.slot_id, "Patient A",
                visit_reason="Chest discomfort", visit_reason_details="Started yesterday",
            )
            self.assertTrue(result["success"])
            self.assertRegex(result["appointment_reference"], r"^VY-\d{4}-\d{5}$")
            self.assertRegex(result["checkin_code"], r"^[0-9]{6}$")
            self.assertNotIn("phone_number", result)
            appointment = db.query(Appointment).filter_by(id=result["appointment_id"]).one()
            self.assertEqual(appointment.visit_reason, "Chest discomfort")
            self.assertEqual(appointment.visit_reason_details, "Started yesterday")
            self.assertEqual(appointment.appointment_reference, result["appointment_reference"])
            self.assertEqual(appointment.checkin_code, result["checkin_code"])

    def test_reference_allocator_retries_a_collision_and_database_keeps_unique_values(self):
        other_doctor, other_slot = self.make_slot("Dr. Other", "Cardiology", "10:00 AM")
        with patch("app.tools.secrets.randbelow", side_effect=[12345, 111111, 12345, 54321, 222222]):
            with self.Session() as db:
                first = self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient A")
                second = self.book(db, "8123456789", other_doctor, other_slot, "Patient B")
                self.assertTrue(first["success"])
                self.assertTrue(second["success"])
                self.assertNotEqual(first["appointment_reference"], second["appointment_reference"])
                self.assertEqual(db.query(Appointment.appointment_reference).filter(Appointment.appointment_reference.isnot(None)).distinct().count(), 2)

    def test_health_concern_options_and_emergency_escalation(self):
        concerns = main.get_health_concerns()
        self.assertEqual(concerns, [
            "Fever", "Headache", "Cough or cold", "Stomach pain", "Skin concern or rash",
            "Menstrual concern", "Joint or back pain", "Eye concern", "Ear, nose, or throat concern",
            "Child health concern", "Routine check-up", "Other",
        ])
        with self.Session() as db:
            rejected = self.book(
                db, "9123456789", self.doctor_id, self.slot_id, "Patient A",
                visit_reason="Routine check-up", health_concern="Other", health_concern_details="I have chest pain",
            )
            self.assertFalse(rejected["success"])
            self.assertEqual(rejected["code"], "emergency_care")
            self.assertIsNone(rejected.get("appointment_reference"))
            self.assertEqual(db.query(Appointment).count(), 0)
        from app.health_concerns import is_emergency_warning
        self.assertFalse(is_emergency_warning("I do not have chest pain"))
        self.assertFalse(is_emergency_warning("No breathing difficulty"))

    def test_each_voice_call_has_a_unique_clean_session_and_masks_phone_transcripts(self):
        connection = SimpleNamespace()
        first = bot.new_voice_session_state(connection, "Name only")
        first["confirmed_phone"] = "9123456789"
        first["patient_name"] = "Patient A"
        second = bot.new_voice_session_state(connection, "Name only")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertIsNone(second["confirmed_phone"])
        self.assertIsNone(second["patient_name"])
        self.assertIsNone(second["selected_slot"])
        self.assertIsNone(second["phone_candidate"])
        record_user_transcript(second, "My mobile number is 9123456789")
        self.assertNotIn("9123456789", second["latest_user_text"])
        self.assertNotIn("9123456789", " ".join(second["caller_transcripts"]))
        self.assertEqual(second["phone_candidate"], "9123456789")

    def test_slot_yes_selects_only_one_spoken_offer_and_cannot_skip_intake(self):
        record_user_transcript(self.state, "I am booking for myself")
        self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        self.offer_test_slot()
        args = {
            "booking_for": "self", "phone_number": "9123456789", "doctor_id": self.doctor_id,
            "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up",
            "health_concern": "Routine check-up",
        }
        result = self.call(voice_tools.book_handler, args)
        self.assertFalse(result["success"])
        self.assertIn("full name", result["message"])
        self.assertEqual(self.state["selected_slot"]["slot_id"], self.slot_id)
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_recorded_slot_selection_is_not_reconfirmed_but_final_booking_confirmation_remains(self):
        record_user_transcript(self.state, "I am booking for myself")
        self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        selection = self.offer_test_slot()

        # Slot choice is the one slot confirmation. The tool directs Gemini
        # straight into intake instead of prompting for the slot a second time.
        self.assertEqual(self.state["selected_slot"]["slot_id"], self.slot_id)
        self.assertEqual(self.state["selected_slot_transcript_sequence"], self.state["transcript_sequence"])
        self.assertTrue(selection["slot_selection_recorded"])
        self.assertFalse(selection["slot_confirmation_required"])
        self.assertIn("Do not read these details back", selection["next_step"])

        record_user_transcript(self.state, "My full name is Patient A")
        self.call(voice_tools.set_patient_name_handler, {"patient_name": "Patient A"})
        self.prepare_cardio_reason("Patient A")
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "Yes, that is correct")
        self.assertTrue(self.call(voice_tools.confirm_phone_handler, {})["success"])
        staged = self.call(voice_tools.book_handler, {
            "booking_for": "self", "phone_number": "9123456789", "doctor_id": self.doctor_id,
            "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up",
            "health_concern": "Routine check-up",
        })
        self.assertTrue(staged["confirmation_required"], "the required final booking confirmation must remain")
        self.assertIn("explicit final confirmation", staged["message"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_booking_rejects_missing_health_concern_after_current_call_phone_confirmation(self):
        self.prepare_self_booking()
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "Yes")
        self.call(voice_tools.confirm_phone_handler, {})
        self.state["health_concern"] = None
        args = {
            "booking_for": "self", "phone_number": "9123456789", "doctor_id": self.doctor_id,
            "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up",
            "health_concern": "Routine check-up",
        }
        success_events = []
        self.state["notify_booking_succeeded"] = success_events.append
        result = self.call(voice_tools.book_handler, args)
        self.assertFalse(result["success"])
        self.assertIn("health concern", result["message"])
        self.assertEqual(success_events, [])
        self.assertIsNone(self.state["last_action_result"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_booking_rejects_a_doctor_or_slot_other_than_the_caller_selected(self):
        other_doctor, other_slot = self.make_slot("Dr. Other", "Cardiology", "10:00 AM")
        self.prepare_self_booking()
        record_user_transcript(self.state, "My full name is Patient A")
        self.call(voice_tools.set_patient_name_handler, {"patient_name": "Patient A"})
        self.prepare_cardio_reason("Patient A")
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "yes")
        self.call(voice_tools.confirm_phone_handler, {})
        args = {
            "booking_for": "self", "phone_number": "9123456789", "doctor_id": other_doctor,
            "slot_id": other_slot, "patient_name": "Patient A", "visit_reason": "Routine check-up",
            "health_concern": "Routine check-up",
        }
        result = self.call(voice_tools.book_handler, args)
        self.assertFalse(result["success"])
        self.assertIn("exact doctor and slot", result["message"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_emergency_transcript_prevents_voice_booking(self):
        record_user_transcript(self.state, "I am booking for myself")
        self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        record_user_transcript(self.state, "I have severe breathing difficulty")
        result = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2099-01-01"})
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "emergency_care")

    def test_visit_reason_options_are_speciality_specific_and_invalid_reason_blocks_booking(self):
        options = main.get_visit_reasons()
        self.assertIn("Chest discomfort", options["Cardiology"])
        self.assertIn("Acne", options["Dermatology"])
        with self.Session() as db:
            rejected = self.book(
                db, "9123456789", self.doctor_id, self.slot_id, "Patient A",
                visit_reason="Acne",
            )
            self.assertFalse(rejected["success"])
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_duplicate_identity_is_patient_number_not_booking_contact(self):
        other_doctor, other_slot = self.make_slot("Dr. ENT", "ENT", "09:00 AM")
        with self.Session() as db:
            self.assertTrue(self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient")["success"])
            conflict = self.book(
                db, "9123456789", other_doctor, other_slot, "Patient", "Different Booker"
            )
            self.assertEqual(conflict["code"], "patient_time_conflict")
            # Using the arranging caller's different number would miss the
            # conflict; the API must receive the patient's number above.
            wrongly_substituted = self.book(
                db, "8123456789", other_doctor, other_slot, "Patient", "Different Booker"
            )
            self.assertTrue(wrongly_substituted["success"])

    def test_additive_seed_migration_preserves_existing_records_and_is_idempotent(self):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker

        legacy_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with legacy_engine.begin() as connection:
            connection.execute(text("CREATE TABLE doctors (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, speciality VARCHAR NOT NULL, experience INTEGER)"))
            connection.execute(text("CREATE TABLE time_slots (id INTEGER PRIMARY KEY, doctor_id INTEGER NOT NULL, date VARCHAR NOT NULL, time VARCHAR NOT NULL, status VARCHAR)"))
            connection.execute(text("CREATE TABLE appointments (id INTEGER PRIMARY KEY, patient_name VARCHAR, phone_number VARCHAR NOT NULL, doctor_id INTEGER NOT NULL, slot_id INTEGER NOT NULL, status VARCHAR)"))
            connection.execute(text("INSERT INTO doctors VALUES (77, 'Legacy Doctor', 'ENT', 4)"))
            connection.execute(text("INSERT INTO time_slots VALUES (88, 77, '2099-01-01', '08:00 AM', 'booked')"))
            connection.execute(text("INSERT INTO appointments VALUES (99, 'Legacy Patient', '9123456789', 77, 88, 'booked')"))

        original_engine, original_session = main.engine, main.SessionLocal
        main.engine = legacy_engine
        main.SessionLocal = sessionmaker(bind=legacy_engine, autoflush=False, autocommit=False)
        try:
            main.initialize_database()
            with main.SessionLocal() as db:
                before = db.query(TimeSlot).count()
                appointment = db.query(Appointment).filter_by(id=99).one()
                self.assertEqual((appointment.patient_name, appointment.phone_number, appointment.status), ("Legacy Patient", "9123456789", "booked"))
                self.assertEqual(appointment.booked_by_name, None)
                self.assertIsNone(appointment.health_concern)
                self.assertIsNone(appointment.health_concern_details)
                self.assertIsNone(appointment.appointment_reference)
                self.assertIsNone(appointment.checkin_code)
                self.assertEqual(db.query(Doctor).filter_by(id=77).one().consultation_fee, 500)
                self.assertEqual(len(db.query(Doctor).all()), 21)
            main.initialize_database()
            with main.SessionLocal() as db:
                self.assertEqual(db.query(Doctor).count(), 21)
                self.assertEqual(db.query(TimeSlot).count(), before)
                self.assertEqual(db.query(Appointment).count(), 1)
        finally:
            main.engine, main.SessionLocal = original_engine, original_session
            legacy_engine.dispose()

    def test_phone_booking_confirmation_and_duplicate_protection(self):
        args = {"booking_for": "self", "phone_number": "9123456789", "doctor_id": self.doctor_id, "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up", "health_concern": "Routine check-up"}
        rejected = self.call(voice_tools.book_handler, args)
        self.assertFalse(rejected["success"])
        self.state["confirmed_phone"] = "8123456789"
        record_user_transcript(self.state, "I am booking for myself")
        started = self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        self.assertTrue(started["success"])
        self.assertIsNone(self.state["confirmed_phone"], "a new booking must require a fresh phone confirmation")
        self.assertIsNone(started["patient_name"])
        self.offer_test_slot()
        record_user_transcript(self.state, "My full name is Patient A")
        self.call(voice_tools.set_patient_name_handler, {"patient_name": "Patient A"})
        self.prepare_cardio_reason("Patient A")
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True  # the verification prompt finished speaking
        self.assertIsNone(self.state["confirmed_phone"])
        record_user_transcript(self.state, "Yes, please.")
        self.assertTrue(self.call(voice_tools.confirm_phone_handler, {})["success"])
        staged = self.call(voice_tools.book_handler, args)
        self.assertTrue(staged["confirmation_required"])
        self.assertFalse(staged["success"])
        record_user_transcript(self.state, "Haan")
        booking_events = []
        self.state["notify_booking_succeeded"] = booking_events.append
        booked = self.call(voice_tools.book_handler, args)
        self.assertTrue(booked["success"])
        self.assertNotIn("phone_number", booked)
        self.assertEqual(booking_events, ["9123456789"])
        self.call(voice_tools.book_handler, args)
        record_user_transcript(self.state, "yes")
        duplicate = self.call(voice_tools.book_handler, args)
        self.assertFalse(duplicate["success"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 1)

    def test_model_cannot_reuse_a_stale_phone_when_caller_accepts_a_slot(self):
        self.prepare_self_booking()
        stale_number = "9123456789"
        args = {
            "booking_for": "self", "phone_number": stale_number,
            "doctor_id": self.doctor_id, "slot_id": self.slot_id,
            "patient_name": "Patient A", "visit_reason": "Other",
        }
        record_user_transcript(self.state, "That time works for me")
        response = self.call(voice_tools.book_handler, args)
        self.assertFalse(response["success"])
        self.assertIn("current call", response["message"])
        self.assertNotIn(stale_number, response["message"])
        self.assertIsNone(self.state["confirmed_phone"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_cancellation_checks_number_confirmation_and_releases_slot(self):
        with self.Session() as db:
            appointment = Appointment(phone_number="9123456780", doctor_id=self.doctor_id, slot_id=self.slot_id, status="booked")
            db.add(appointment)
            db.query(TimeSlot).filter_by(id=self.slot_id).update({"status": "booked"})
            db.commit()
            appt_id = appointment.id
        self.state["confirmed_phone"] = "9123456780"
        appointments = self.call(voice_tools.list_active_appointments_handler, {})
        self.assertEqual(appointments["appointments"][0]["appointment_id"], appt_id)
        wrong = self.call(voice_tools.cancel_handler, {"phone_number": "8123456789", "appointment_id": appt_id})
        self.assertFalse(wrong["success"])
        staged = self.call(voice_tools.cancel_handler, {"phone_number": "9123456780", "appointment_id": appt_id})
        self.assertTrue(staged["confirmation_required"])
        record_user_transcript(self.state, "yes, that's right")
        cancelled = self.call(voice_tools.cancel_handler, {"phone_number": "9123456780", "appointment_id": appt_id})
        self.assertTrue(cancelled["success"])
        with self.Session() as db:
            self.assertEqual(db.query(TimeSlot).filter_by(id=self.slot_id).one().status, "available")

    def test_nonaffirmative_turn_invalidates_staged_phone_and_action(self):
        self.submit_phone("9123456789")
        record_user_transcript(self.state, "Actually, I gave the wrong number")
        self.assertIsNone(self.state["pending_phone"])
        record_user_transcript(self.state, "yes")
        self.assertFalse(self.call(voice_tools.confirm_phone_handler, {})["success"])

        # Even if an unrelated later utterance is affirmative, it cannot approve
        # an older booking prompt that the caller declined or changed.
        self.prepare_self_booking()
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "yes")
        args = {"booking_for": "self", "phone_number": "9123456789", "doctor_id": self.doctor_id, "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up", "health_concern": "Routine check-up"}
        first = self.call(voice_tools.book_handler, args)
        self.assertTrue(first["confirmation_required"])
        record_user_transcript(self.state, "No, let me think")
        self.assertIsNone(self.state["pending_booking"])
        record_user_transcript(self.state, "yes")
        second = self.call(voice_tools.book_handler, args)
        self.assertTrue(second["confirmation_required"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_phone_confirmation_is_deterministic_armed_and_correction_replaces_pending_number(self):
        first = "9123456789"
        replacement = "8123456780"
        self.submit_phone(first)
        record_user_transcript(self.state, "Yes, it is")
        self.assertIsNone(self.state.get("confirmed_phone"), "an unsolicited yes before the spoken check cannot confirm")
        self.assertEqual(self.state["pending_phone"], first)

        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "Yes, you are correct. Please confirm.")
        self.assertEqual(self.state["confirmed_phone"], first)
        self.assertTrue(self.call(voice_tools.confirm_phone_handler, {})["success"])

        record_user_transcript(self.state, "The number was wrong; I need to change the phone number")
        self.assertIsNone(self.state["confirmed_phone"])
        self.submit_phone(replacement)
        self.assertIsNone(self.state["confirmed_phone"])
        self.assertEqual(self.state["pending_phone"], replacement)
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "Yes, yes")
        self.assertEqual(self.state["confirmed_phone"], replacement)
        self.assertTrue(self.call(voice_tools.confirm_phone_handler, {})["success"])

    def test_phone_confirmation_no_never_confirms_and_clears_old_pending_number(self):
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "No, that's not correct")
        self.assertIsNone(self.state["confirmed_phone"])
        self.assertIsNone(self.state["pending_phone"])
        self.assertFalse(self.call(voice_tools.confirm_phone_handler, {})["success"])

    def test_phone_confirmation_prompt_arms_only_after_tts_finishes(self):
        self.assertTrue(bot.asks_to_verify_phone("Your number ends in 6789. Is that correct?"))
        self.assertTrue(bot.asks_to_verify_phone("Please confirm that the phone number is correct."))
        self.assertFalse(bot.asks_to_verify_phone("The phone number has been confirmed."))
        processor = bot.EndCallAfterTTS({"phone_prompt_after_tts": True})
        processor.state["phone_confirmation_armed"] = False
        pushed = []
        async def push(frame, direction): pushed.append(frame)
        processor.push_frame = push
        coroutine = processor.process_frame(TTSStoppedFrame(), FrameDirection.DOWNSTREAM)
        with self.assertRaises(StopIteration): coroutine.send(None)
        self.assertTrue(processor.state["phone_confirmation_armed"])

        processor.state["phone_prompt_after_tts"] = True
        original_interruption = FrameProcessor._start_interruption
        async def noop_interruption(self): return None
        try:
            FrameProcessor._start_interruption = noop_interruption
            coroutine = processor.process_frame(InterruptionFrame(), FrameDirection.UPSTREAM)
            with self.assertRaises(StopIteration): coroutine.send(None)
        finally:
            FrameProcessor._start_interruption = original_interruption
        self.assertFalse(processor.state["phone_prompt_after_tts"])

    def test_booking_for_someone_else_requires_patient_name_and_confirmed_phone(self):
        self.state["display_name"] = "Arranging Caller"
        record_user_transcript(self.state, "This is for my daughter")
        started = self.call(voice_tools.begin_booking_handler, {"booking_for": "someone_else"})
        self.assertTrue(started["success"])
        self.assertIsNone(started["patient_name"])
        args = {"booking_for": "someone_else", "phone_number": "9123456789", "doctor_id": self.doctor_id, "slot_id": self.slot_id, "patient_name": "Patient B", "visit_reason": "Routine check-up", "health_concern": "Routine check-up"}
        missing_name = self.call(voice_tools.book_handler, args)
        self.assertFalse(missing_name["success"])
        self.assertIn("full name", missing_name["message"])
        self.offer_test_slot()
        record_user_transcript(self.state, "Her full name is Patient B")
        self.call(voice_tools.set_patient_name_handler, {"patient_name": "Patient B"})
        self.prepare_cardio_reason("Patient B")
        unconfirmed = self.call(voice_tools.book_handler, args)
        self.assertFalse(unconfirmed["success"])
        self.assertIn("10-digit number now", unconfirmed["message"])
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        record_user_transcript(self.state, "yes")
        self.assertTrue(self.call(voice_tools.confirm_phone_handler, {})["success"])
        needs_final_confirmation = self.call(voice_tools.book_handler, args)
        self.assertTrue(needs_final_confirmation["confirmation_required"])
        record_user_transcript(self.state, "yes, I confirm")
        booked = self.call(voice_tools.book_handler, args)
        self.assertTrue(booked["success"])
        with self.Session() as db:
            appointment = db.query(Appointment).one()
            self.assertEqual(appointment.patient_name, "Patient B")
            self.assertIsNone(appointment.booked_by_name, "a saved display name is a greeting label, not verified arranger identity")

    def test_personalized_greeting_and_missing_name_fallback(self):
        self.assertIn("'Keerthi'", bot.greeting_instruction("Keerthi"))
        self.assertIn("greet them by name", bot.greeting_instruction("Keerthi").lower())
        generic = bot.greeting_instruction("")
        self.assertIn("generic greeting", generic)
        self.assertNotIn("Keerthi", generic)
        self.assertEqual(main._display_name_from_request_data({"display_name": "  Keerthi\nRao  "}), "Keerthi Rao")
        self.assertEqual(main._display_name_from_request_data({"display_name": "\u0000"}), "")
        class Context:
            messages = []
            def add_message(self, message): self.messages.append(message)
        class TTS:
            frames = []
            async def queue_frame(self, frame, direction): self.frames.append((frame, direction))
        context, tts = Context(), TTS()
        state = {"display_name": "Keerthi", "greeting_started": False}
        with self.assertRaises(StopIteration) as first_greeting:
            bot.start_session_greeting(state, context, tts).send(None)
        with self.assertRaises(StopIteration) as reconnect_greeting:
            bot.start_session_greeting(state, context, tts).send(None)
        self.assertTrue(first_greeting.exception.value)
        self.assertFalse(reconnect_greeting.exception.value)
        self.assertEqual(len(context.messages), 1)
        self.assertIn("Keerthi", context.messages[0]["content"])
        self.assertEqual(len(tts.frames), 1)
        self.assertIn("Hi, Keerthi!", tts.frames[0][0].text)
        fallback = bot.greeting_text("")
        self.assertIn("what would you like me to call you", fallback.lower())
        self.assertNotIn("Keerthi", fallback)

    def test_webrtc_request_display_name_reaches_voice_session(self):
        received = []
        original_handler, original_start = main.webrtc_handler, main.on_webrtc_connection
        class RequestHandler:
            async def handle_web_request(self, request, callback):
                await callback("test-connection")
                return {"sdp": "answer", "type": "answer", "pc_id": "test-pc"}
        async def start(connection, display_name):
            received.append((connection, display_name))
        try:
            main.webrtc_handler = RequestHandler()
            main.on_webrtc_connection = start
            request = main.SmallWebRTCRequest(
                sdp="offer", type="offer", request_data={"display_name": "Keerthi Rao"}
            )
            coroutine = main.handle_offer(request)
            with self.assertRaises(StopIteration) as completed:
                coroutine.send(None)
            self.assertEqual(completed.exception.value["pc_id"], "test-pc")
            self.assertEqual(received, [("test-connection", "Keerthi Rao")])
        finally:
            main.webrtc_handler, main.on_webrtc_connection = original_handler, original_start

    def test_confirmation_phrases_and_call_closing_require_caller_words(self):
        for phrase in (
            "Yes, it is.", "Yes, you are correct. Please confirm.", "Yes.", "Yes, yes.",
            "That's correct.", "Yes, please confirm.", "Yes, I'm confirming my appointment",
        ):
            self.assertTrue(voice_tools.is_explicit_confirmation(phrase), phrase)
        for phrase in ("No.", "No, that's wrong.", "yes, but wait", "I think so", "not yet"):
            self.assertFalse(voice_tools.is_explicit_confirmation(phrase))
        self.state["latest_user_text"] = "That's all, thank you"
        response = self.call(voice_tools.end_voice_session_handler, {})
        self.assertTrue(response["success"])
        self.assertTrue(self.state["end_after_assistant_response"])
        self.state["end_after_assistant_response"] = False
        self.state["latest_user_text"] = "Maybe later"
        self.assertFalse(self.call(voice_tools.end_voice_session_handler, {})["success"])

    def test_specific_doctor_requires_exact_available_match(self):
        dr_rahul, _ = self.make_slot("Dr. Rahul Sharma", "Dermatology", "10:00 AM")
        record_user_transcript(self.state, "I want Dr. Rohit Sharma")
        response = self.call(voice_tools.check_availability_handler, {"doctor_name": "Dr. Rohit Sharma"})
        self.assertTrue(response["clarification_required"])
        self.assertIn("Dr. Rahul Sharma", response["similar_doctors"])
        self.assertNotIn((dr_rahul, self.slot_id), self.state["available_slots"])
        record_user_transcript(self.state, "I meant Dr. Rahul Sharma")
        exact = self.call(voice_tools.check_availability_handler, {"doctor_name": "Dr. Rahul Sharma"})
        self.assertTrue(exact["success"])
        self.assertEqual({d["doctor_id"] for d in exact["doctors"]}, {dr_rahul})

    def test_relative_and_yearless_dates_use_asia_kolkata_current_date(self):
        today = date(2026, 11, 25)
        self.assertEqual(
            voice_tools.resolve_appointment_date("2024-11-26", "Tomorrow, which is 26th November", today),
            "2026-11-26",
        )
        self.assertEqual(voice_tools.resolve_appointment_date(None, "26th November", today), "2026-11-26")
        self.assertEqual(voice_tools.resolve_appointment_date(None, "November 26th", today), "2026-11-26")
        self.assertEqual(voice_tools.resolve_appointment_date(None, "today", today), "2026-11-25")
        self.assertEqual(voice_tools.resolve_appointment_date(None, "day after tomorrow", today), "2026-11-27")
        self.assertEqual(voice_tools.resolve_appointment_date("tomorrow", "", today), "2026-11-26")

        requested_zone = []
        class Clock:
            @staticmethod
            def now(tz):
                requested_zone.append(tz.tzname(None))
                return real_datetime(2026, 11, 25, 23, 55, tzinfo=tz)
        with patch.object(voice_tools, "datetime", Clock):
            self.assertEqual(voice_tools.india_today(), today)
        self.assertEqual(requested_zone, ["Asia/Kolkata"])

    def test_availability_handler_overrides_model_year_using_caller_date(self):
        with self.Session() as db:
            slot = TimeSlot(doctor_id=self.doctor_id, date="2026-11-26", time="10:00 AM", status="available")
            db.add(slot)
            db.commit()
            slot_id = slot.id
        self.state["caller_transcripts"] = ["Tomorrow, which is 26th November"]
        self.state["latest_user_text"] = self.state["caller_transcripts"][-1]
        with patch.object(voice_tools, "india_today", return_value=date(2026, 11, 25)):
            result = self.call(
                voice_tools.check_availability_handler,
                {"speciality": "Cardiology", "date": "2024-11-26"},
            )
        self.assertEqual(result["resolved_date"], "2026-11-26")
        self.assertIn(slot_id, [item["slot_id"] for doc in result["doctors"] for item in doc["available_slots"]])
        self.state["caller_transcripts"] = ["26th November"]
        with patch.object(voice_tools, "india_today", return_value=date(2026, 11, 25)):
            yearless = self.call(voice_tools.check_availability_handler, {"speciality": "Cardiology", "date": "2024-11-26"})
        self.assertEqual(yearless["resolved_date"], "2026-11-26")

    def test_availability_maps_dermatologist_to_caller_requested_dermatology(self):
        with self.Session() as db:
            doctor = Doctor(
                name="Dr. Skin Specialist",
                speciality="Dermatology",
                experience=6,
                consultation_fee=600,
            )
            db.add(doctor)
            db.flush()
            slot = TimeSlot(
                doctor_id=doctor.id,
                date="2026-11-26",
                time="10:00 AM",
                status="available",
            )
            db.add(slot)
            db.commit()
            doctor_id, slot_id = doctor.id, slot.id
        self.state["booking_for"] = "self"
        record_user_transcript(
            self.state,
            "I need a Dermatology appointment on November 26, 2026",
        )

        result = self.call(
            voice_tools.check_availability_handler,
            {"speciality": "Dermatologist", "date": "2026-11-26"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["resolved_date"], "2026-11-26")
        self.assertEqual(self.state["speciality"], "Dermatology")
        self.assertEqual([doctor["doctor_id"] for doctor in result["doctors"]], [doctor_id])
        self.assertEqual(
            [slot["slot_id"] for doctor in result["doctors"] for slot in doctor["available_slots"]],
            [slot_id],
        )

    def test_gemini_503_retry_is_once_and_only_before_any_output(self):
        class Immediate:
            def __await__(self):
                if False: yield None
                return None
        original_sleep = bot.asyncio.sleep
        bot.asyncio.sleep = lambda _delay: Immediate()
        def drive(coroutine):
            with self.assertRaises(StopIteration) as completed:
                coroutine.send(None)
            return completed.exception.value
        class ProviderError(Exception):
            code = 503
            status = "UNAVAILABLE"
        calls = []
        async def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise ProviderError()
            yield "response"
        async def run():
            return [item async for item in bot.retry_initial_unavailable(flaky)]
        self.assertEqual(drive(run()), ["response"])
        self.assertEqual(len(calls), 2)

        calls.clear()
        async def fails():
            calls.append(1)
            raise ProviderError()
            yield
        async def run_bounded():
            try:
                return [item async for item in bot.retry_initial_unavailable(fails)]
            except ProviderError:
                return "failed"
        self.assertEqual(drive(run_bounded()), "failed")
        self.assertEqual(len(calls), 2)

        calls.clear()
        async def fails_after_output():
            calls.append(1)
            yield "partial"
            raise ProviderError()
        async def run_no_replay():
            try:
                return [item async for item in bot.retry_initial_unavailable(fails_after_output)]
            except ProviderError:
                return "failed"
        self.assertEqual(drive(run_no_replay()), "failed")
        self.assertEqual(len(calls), 1)
        bot.asyncio.sleep = original_sleep

    def test_voice_response_guard_preserves_tool_results_and_discards_partial_error_text(self):
        guard = bot.CompleteResponseGuard(self.state)
        pushed = []
        async def push(frame, direction): pushed.append((frame, direction))
        guard.push_frame = push
        def run(coroutine):
            with self.assertRaises(StopIteration): coroutine.send(None)
        direction = FrameDirection.DOWNSTREAM
        run(guard.process_frame(LLMFullResponseStartFrame(), direction))
        run(guard.process_frame(LLMTextFrame("partial"), direction))
        tool_result = FunctionCallResultFrame("book_appointment", "tool-1", {}, {"success": True})
        run(guard.process_frame(tool_result, direction))
        run(guard.process_frame(LLMFullResponseEndFrame(), direction))
        self.assertIn(tool_result, [frame for frame, _ in pushed])
        self.assertIn("partial", [frame.text for frame, _ in pushed if isinstance(frame, LLMTextFrame)])

        pushed.clear()
        self.state["last_action_result"] = {
            "type": "booking", "success": True, "doctor": "Dr. Test",
            "date": "2099-01-01", "time": "09:00 AM", "patient_name": "Patient A",
        }
        run(guard.process_frame(LLMFullResponseStartFrame(), direction))
        run(guard.process_frame(LLMTextFrame("Just"), direction))
        run(guard.process_frame(ErrorFrame("temporary provider failure"), direction))
        run(guard.process_frame(LLMFullResponseEndFrame(), direction))
        spoken = [frame.text for frame, _ in pushed if isinstance(frame, TTSSpeakFrame)]
        self.assertEqual(len(spoken), 1)
        self.assertIn("is booked", spoken[0])
        self.assertNotIn("Just", spoken[0])

        self.state["last_action_result"] = None
        self.state["last_action_phone"] = "9123456789"
        scrubbed = guard._safe_text("Your phone is 9 1 2 3 4 5 6 7 8 9; we have the number.")
        self.assertNotIn("9123456789", scrubbed)
        self.assertIn("ending in 6789", scrubbed)
        self.state["pending_phone"] = "9123456789"
        self.assertEqual(
            guard._safe_text("Your phone number is confirmed."),
            "The number ends in 6789. Is that correct?",
        )

    def test_call_ends_only_after_the_closing_tts_stops(self):
        processor = bot.EndCallAfterTTS(self.state)
        self.state["end_after_assistant_response"] = True
        pushed = []
        async def push(frame, direction): pushed.append(frame)
        processor.push_frame = push
        coroutine = processor.process_frame(TTSStoppedFrame(), FrameDirection.DOWNSTREAM)
        with self.assertRaises(StopIteration): coroutine.send(None)
        self.assertIsInstance(pushed[0], TTSStoppedFrame)
        self.assertIsInstance(pushed[1], EndFrame)
        self.assertNotIn("end_after_assistant_response", self.state)

    def test_booking_requires_explicit_patient_kind_and_name(self):
        not_asked = self.call(voice_tools.begin_booking_handler, {"booking_for": "self"})
        self.assertFalse(not_asked["success"])
        self.assertIsNone(self.state["booking_for"])
        self.state["confirmed_phone"] = "9123456789"
        args = {"phone_number": "9123456789", "doctor_id": self.doctor_id, "slot_id": self.slot_id, "patient_name": "Patient A", "visit_reason": "Routine check-up", "health_concern": "Routine check-up"}
        result = self.call(voice_tools.book_handler, args)
        self.assertFalse(result["success"])
        self.assertIn("who the appointment is for", result["message"])
        with self.Session() as db:
            self.assertEqual(db.query(Appointment).count(), 0)

    def test_session_transcript_uses_only_final_elevenlabs_frames(self):
        processor = bot.SessionTranscript(self.state)
        pushed = []

        async def push_frame(frame, direction):
            pushed.append((frame, direction))
        processor.push_frame = push_frame

        def run(coroutine):
            with self.assertRaises(StopIteration):
                coroutine.send(None)

        interim = TranscriptionFrame("yes", "caller", "2026-11-25T00:00:00Z", finalized=False)
        final = TranscriptionFrame("yes please", "caller", "2026-11-25T00:00:01Z", finalized=True)
        run(processor.process_frame(interim, FrameDirection.DOWNSTREAM))
        self.assertEqual(self.state["transcript_sequence"], 0)
        self.submit_phone("9123456789")
        self.state["phone_confirmation_armed"] = True
        run(processor.process_frame(final, FrameDirection.DOWNSTREAM))
        self.assertEqual(self.state["transcript_sequence"], 2)
        self.assertEqual(self.state["confirmation_grant"]["kind"], "phone")
        self.assertEqual(len(pushed), 2)

    def test_session_transcript_redacts_phone_digits_before_forwarding_to_gemini(self):
        processor = bot.SessionTranscript(self.state)
        pushed = []
        async def push_frame(frame, direction): pushed.append(frame)
        processor.push_frame = push_frame
        frame = TranscriptionFrame("My mobile number is 9123456789", "caller", "2026-11-25T00:00:01Z", finalized=True)
        coroutine = processor.process_frame(frame, FrameDirection.DOWNSTREAM)
        with self.assertRaises(StopIteration): coroutine.send(None)
        self.assertNotIn("9123456789", frame.text)
        self.assertNotIn("9123456789", self.state["latest_user_text"])
        self.assertNotIn("9123456789", " ".join(self.state["caller_transcripts"]))
        self.assertEqual(self.state["phone_candidate"], "9123456789")
        self.assertEqual(pushed, [frame])

    def test_pipeline_import_and_construction_without_provider_calls(self):
        converted = GeminiLLMAdapter().from_standard_tools(ToolsSchema(standard_tools=APPOINTMENT_TOOLS))
        declarations = converted[0]["function_declarations"]
        self.assertEqual({tool["name"] for tool in declarations}, {tool.name for tool in APPOINTMENT_TOOLS})
        class Noop:
            registered = []
            constructed = []
            instances = []
            outputs = []
            def __init__(self, *args, **kwargs):
                self.constructed.append(kwargs)
                self.event_handlers = {}
                self.instances.append(self)
            def input(self): return object()
            def output(self):
                output = object()
                self.outputs.append(output)
                return output
            def register_function(self, *args, **kwargs): self.registered.append(args[0])
            def event_handler(self, name):
                def decorator(handler):
                    self.event_handlers[name] = handler
                    return handler
                return decorator
        class NoopContext:
            instances = []
            def __init__(self, **kwargs):
                self.messages = []
                self.tools = kwargs.get("tools")
                self.instances.append(self)
            def add_message(self, message): self.messages.append(message)
        class NoopAggregatorProcessor:
            pass
        class NoopAggregators:
            instances = []
            def __init__(self, context, **kwargs):
                self.context = context
                self.user_processor = NoopAggregatorProcessor()
                self.assistant_processor = NoopAggregatorProcessor()
                self.instances.append(self)
            def user(self): return self.user_processor
            def assistant(self): return self.assistant_processor
        class NoopPipeline:
            def __init__(self, processors): self.processors = processors
        class NoopTask:
            instances = []
            def __init__(self, pipeline, **kwargs):
                self.pipeline, self.kwargs = pipeline, kwargs
                self.instances.append(self)
        class NoopRunner:
            def run(self, task):
                self.task = task
                class Immediate:
                    def __await__(self):
                        if False: yield None
                        return None
                return Immediate()
        # Mock provider constructors/runner so construction tests do not need credentials or network.
        patches = [("SmallWebRTCTransport", Noop), ("ElevenLabsRealtimeSTTService", Noop),
                   ("ResilientGoogleLLMService", Noop), ("ElevenLabsTTSService", Noop),
                   ("PipelineTask", NoopTask), ("PipelineRunner", NoopRunner),
                   ("Pipeline", NoopPipeline), ("LLMContext", NoopContext),
                   ("LLMContextAggregatorPair", NoopAggregators)]
        originals = [(name, getattr(bot, name)) for name, _ in patches]
        original_credentials = (bot.GOOGLE_API_KEY, bot.ELEVENLABS_API_KEY, bot.ELEVENLABS_VOICE_ID)
        try:
            Noop.registered.clear()
            Noop.constructed.clear()
            Noop.instances.clear()
            Noop.outputs.clear()
            NoopContext.instances.clear()
            NoopAggregators.instances.clear()
            NoopTask.instances.clear()
            for name, replacement in patches: setattr(bot, name, replacement)
            bot.GOOGLE_API_KEY = "mock"; bot.ELEVENLABS_API_KEY = "mock"; bot.ELEVENLABS_VOICE_ID = "mock"
            coroutine = bot.create_voice_pipeline(object(), display_name="Keerthi")
            with self.assertRaises(StopIteration):
                coroutine.send(None)
            self.assertEqual({tool.name for tool in APPOINTMENT_TOOLS} >= {"check_doctor_availability", "begin_booking", "set_patient_name", "book_appointment", "cancel_appointment"}, True)
            self.assertEqual(set(Noop.registered), {tool.name for tool in APPOINTMENT_TOOLS})
            self.assertIn("list_active_appointments", Noop.registered)
            transport = next(instance for instance in Noop.instances if "on_client_connected" in instance.event_handlers)
            self.assertTrue(callable(transport.event_handlers["on_client_connected"]))
            self.assertTrue(any(item.get("stream_idle_timeout_secs") == 90.0 for item in Noop.constructed))
            self.assertTrue(any(getattr(item.get("commit_strategy"), "value", None) == "manual" for item in Noop.constructed))
            self.assertTrue(any(item.get("retry_timeout_secs") == 30.0 and item.get("retry_on_timeout") is True and item.get("run_in_parallel") is False for item in Noop.constructed))
            processors = NoopTask.instances[-1].pipeline.processors
            end_call_index = next(i for i, processor in enumerate(processors) if isinstance(processor, bot.EndCallAfterTTS))
            self.assertIs(processors[end_call_index + 1], Noop.outputs[-1])
        finally:
            for name, original in originals: setattr(bot, name, original)
            bot.GOOGLE_API_KEY, bot.ELEVENLABS_API_KEY, bot.ELEVENLABS_VOICE_ID = original_credentials

    def test_http_route_functions_and_appointment_lifecycle(self):
        registered = {(route.path, method) for route in main.app.routes for method in (route.methods or set())}
        for path, method in [('/', 'GET'), ('/health', 'GET'), ('/docs', 'GET'), ('/openapi.json', 'GET'),
                             ('/api/doctors', 'GET'), ('/api/availability', 'GET'), ('/api/health-concerns', 'GET'),
                             ('/api/appointments', 'POST'), ('/api/appointments/cancel', 'POST'), ('/api/appointments', 'GET'),
                             ('/api/offer', 'POST'), ('/api/offer', 'PATCH')]:
            self.assertIn((path, method), registered)
        # The voice availability handler also returns its result through
        # Pipecat's callback path.
        voice_availability = self.call(
            voice_tools.check_availability_handler,
            {"speciality": "Cardiology", "date": "2099-01-01"},
        )
        self.assertTrue(voice_availability["success"])
        self.assertEqual(voice_availability["doctors"][0]["available_slots"][0]["slot_id"], self.slot_id)
        with self.Session() as db:
            self.assertEqual(main.home()["message"].startswith("VeyaCare"), True)
            self.assertEqual(main.health_check()["status"], "healthy")
            self.assertEqual(main.get_doctors(db)[0]["name"], "Dr. Test")
            self.assertEqual(len(main.get_availability("Cardiology", "2099-01-01", db)), 1)
            payload = BookingRequest(phone_number="9123456789", doctor_id=self.doctor_id, slot_id=self.slot_id, patient_name="Patient One", visit_reason="Routine check-up", health_concern="Routine check-up")
            booked_result = main.create_appointment(payload, db)
            self.assertTrue(booked_result["success"])
            self.assertRegex(booked_result["appointment_reference"], r"^VY-\d{4}-\d{5}$")
            self.assertRegex(booked_result["checkin_code"], r"^[0-9]{6}$")
            with self.assertRaises(HTTPException) as duplicate:
                main.create_appointment(payload, db)
            self.assertEqual(duplicate.exception.status_code, 409)
            listing = main.get_appointments("9123456789", db)
            self.assertNotIn("phone_number", listing[0], "appointment responses must not expose the full phone number")
            wrong = CancellationRequest(phone_number="8123456789", appointment_id=listing[0]["id"])
            with self.assertRaises(HTTPException) as mismatch:
                main.remove_appointment(wrong, db)
            self.assertEqual(mismatch.exception.status_code, 404)
            cancellation = CancellationRequest(phone_number="9123456789", appointment_id=listing[0]["id"])
            self.assertTrue(main.remove_appointment(cancellation, db)["success"])
            self.assertEqual(main.get_availability(None, "2099-01-01", db)[0]["available_slots"][0]["slot_id"], self.slot_id)

    def test_patient_lookup_is_scoped_and_cancelled_rows_leave_active_choices(self):
        other_doctor, other_slot = self.make_slot("Dr. Other", "Dermatology", "10:00 AM")
        with self.Session() as db:
            own = self.book(db, "9123456789", self.doctor_id, self.slot_id, "Patient One")
            other = self.book(db, "8123456789", other_doctor, other_slot, "Patient Two")
            own_rows = main.get_appointments("9123456789", db)
            other_rows = main.get_appointments("8123456789", db)
            self.assertEqual([row["id"] for row in own_rows], [own["appointment_id"]])
            self.assertEqual([row["id"] for row in other_rows], [other["appointment_id"]])
            self.assertEqual((own_rows[0]["doctor"], own_rows[0]["speciality"], own_rows[0]["patient_name"]), ("Dr. Test", "Cardiology", "Patient One"))
            self.assertTrue(main.remove_appointment(CancellationRequest(phone_number="9123456789", appointment_id=own["appointment_id"]), db)["success"])
            self.assertEqual(main.get_appointments("9123456789", db)[0]["status"], "cancelled")
            self.assertFalse(any(row["status"] == "booked" for row in main.get_appointments("9123456789", db)))

    def test_legacy_eleven_digit_appointment_is_not_exposed_or_accepted_by_normal_lookup(self):
        with self.Session() as db:
            legacy = Appointment(phone_number="91912345678", doctor_id=self.doctor_id, slot_id=self.slot_id, status="booked", patient_name="Legacy Patient")
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
            # Exact valid ten-digit lookups do not coerce, truncate, or expose it.
            self.assertEqual(main.get_appointments("9123456789", db), [])
            self.assertFalse(is_valid_indian_mobile(legacy.phone_number))
            stored = db.query(Appointment).filter_by(id=legacy_id).one()
            self.assertEqual((stored.phone_number, stored.status), ("91912345678", "booked"))
            with self.assertRaises(HTTPException) as invalid:
                main.get_appointments("91912345678", db)
            self.assertEqual(invalid.exception.status_code, 422)

    def test_cors_preflight_allows_both_loopback_origins_without_wildcards(self):
        middleware_config = next(
            item for item in main.app.user_middleware if item.cls is CORSMiddleware
        )
        self.assertEqual(
            middleware_config.kwargs["allow_origins"],
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
        self.assertFalse(middleware_config.kwargs["allow_credentials"])
        self.assertNotIn("*", middleware_config.kwargs["allow_origins"])

        async def downstream(_scope, _receive, _send):
            raise AssertionError("A CORS preflight should be answered by the middleware")

        def preflight(origin, method="GET"):
            messages = []
            middleware = CORSMiddleware(downstream, **middleware_config.kwargs)

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http",
                "method": "OPTIONS",
                "path": "/health",
                "headers": [
                    (b"origin", origin.encode("ascii")),
                    (b"access-control-request-method", method.encode("ascii")),
                    (b"access-control-request-headers", b"content-type"),
                ],
            }
            coroutine = middleware(scope, receive, send)
            with self.assertRaises(StopIteration):
                coroutine.send(None)
            response = next(message for message in messages if message["type"] == "http.response.start")
            return response["status"], dict(response["headers"])

        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            for method in ("GET", "POST", "PATCH"):
                status, headers = preflight(origin, method)
                self.assertEqual(status, 200)
                self.assertEqual(headers[b"access-control-allow-origin"].decode(), origin)
                self.assertIn(method.encode("ascii"), headers[b"access-control-allow-methods"])

        blocked_status, _ = preflight("http://evil.example")
        self.assertEqual(blocked_status, 400)

    def test_startup_seeds_empty_database(self):
        original_engine, original_session = main.engine, main.SessionLocal
        seed_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        main.engine = seed_engine
        main.SessionLocal = sessionmaker(bind=seed_engine)
        try:
            main.initialize_database()
            with main.SessionLocal() as db:
                self.assertGreaterEqual(db.query(Doctor).count(), 4)
                self.assertGreater(db.query(TimeSlot).count(), 0)
        finally:
            main.engine, main.SessionLocal = original_engine, original_session
            seed_engine.dispose()


if __name__ == "__main__":
    unittest.main()
