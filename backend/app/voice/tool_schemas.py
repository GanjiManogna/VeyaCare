from pipecat.adapters.llm.schemas.function_schema import FunctionSchema

# Pipecat 1.17's Gemini adapter converts standard FunctionSchema values to
# Gemini function declarations. Keep phone numbers as strings for leading zeros.
APPOINTMENT_TOOLS = [
    FunctionSchema(
        name="get_visit_reason_options",
        description="After the caller chooses a speciality, return that speciality's real clinic visit-reason options. These are reasons only, never diagnoses. Always mention Other and allow free wording.",
        properties={"speciality": {"type": "string", "description": "A speciality the caller explicitly requested."}},
        required=["speciality"],
    ),
    FunctionSchema(
        name="set_visit_reason",
        description="Legacy alias for recording one caller-selected health concern category after slot selection; this is intake routing, not a diagnosis.",
        properties={
            "visit_reason": {"type": "string", "description": "One returned reason option, or Other."},
            "visit_reason_details": {"type": "string", "description": "Optional brief description in the caller's own words."},
        },
        required=["visit_reason"],
    ),
    FunctionSchema(
        name="select_appointment_slot",
        description="Record the exact doctor and time the caller selected from the most recent spoken availability offer. The selection itself confirms that slot: after this tool succeeds, do not repeat the slot or ask for slot confirmation again. Continue intake; this never skips the separate final booking confirmation.",
        properties={"doctor_id": {"type": "integer"}, "slot_id": {"type": "integer"}},
        required=["doctor_id", "slot_id"],
    ),
    FunctionSchema(
        name="get_health_concerns",
        description="Return the curated non-diagnostic health concern categories after a slot is selected.",
        properties={},
        required=[],
    ),
    FunctionSchema(
        name="set_health_concern",
        description="Record the category explicitly selected by the patient. For Other, also record a short patient-described detail. Never diagnose or recommend treatment.",
        properties={
            "health_concern": {"type": "string", "description": "One returned health concern category."},
            "health_concern_details": {"type": "string", "description": "Required short description for Other; otherwise omit."},
        },
        required=["health_concern"],
    ),
    FunctionSchema(
        name="check_doctor_availability",
        description="Find doctors, consultation fees, and real available slots, optionally filtered by speciality and date. Use the clinic's speciality label Dermatology when the caller asks for a dermatologist. Offer only slots returned by this tool.",
        properties={
            "speciality": {"type": "string", "description": "Medical speciality, such as Cardiology."},
            "date": {"type": "string", "description": "Preferred appointment date in YYYY-MM-DD format. Use the server-provided Asia/Kolkata current date for today, tomorrow, and dates without a year; do not invent a year."},
            "doctor_name": {"type": "string", "description": "Exact doctor name spoken by the caller, when they requested a specific doctor."},
        },
        required=[],
    ),
    FunctionSchema(
        name="begin_booking",
        description="After asking whether the appointment is for the caller or someone else, begin a fresh booking. This clears any previously confirmed phone number. Use self or someone_else exactly.",
        properties={
            "booking_for": {"type": "string", "enum": ["self", "someone_else"], "description": "Whether the patient is the caller or another person."},
        },
        required=["booking_for"],
    ),
    FunctionSchema(
        name="set_patient_name",
        description="Record the patient's full name after the caller selects a slot and says the name. Never use the display name as patient identity.",
        properties={
            "patient_name": {"type": "string", "description": "Full name of the actual patient receiving care."},
        },
        required=["patient_name"],
    ),
    FunctionSchema(
        name="list_active_appointments",
        description="List active appointments for the phone number confirmed in this voice session. Use this before helping the caller choose an appointment to cancel.",
        properties={},
        required=[],
    ),
    FunctionSchema(
        name="set_phone_number",
        description="Read the latest caller utterance's securely captured phone candidate, validate exactly 10 ASCII digits starting with 6-9, store it pending, and ask to verify only its last four digits. Leave phone_number unset; never reuse a number from context.",
        properties={"phone_number": {"type": "string", "description": "Optional compatibility field; server ignores it and uses only digits securely captured from the latest caller utterance."}},
        required=[],
    ),
    FunctionSchema(
        name="confirm_phone_number",
        description="Return confirmation status for the pending phone number. The server accepts a clear affirmative only after its phone verification prompt finished speaking; a no/correction never confirms it.",
        properties={},
        required=[],
    ),
    FunctionSchema(
        name="book_appointment",
        description="After all required intake and phone confirmation, present the one final concise summary of patient, health concern, selected doctor/date/time, fee, and phone last four. Ask for explicit final booking confirmation once, then retry with identical details only after a clear yes. Do not add a separate repeated slot confirmation.",
        properties={
            "booking_for": {"type": "string", "enum": ["self", "someone_else"]},
            "phone_number": {"type": "string", "description": "Phone number confirmed during this voice session."},
            "doctor_id": {"type": "integer"},
            "slot_id": {"type": "integer"},
            "patient_name": {"type": "string", "description": "Full name of the patient receiving the appointment."},
            "booked_by_name": {"type": "string", "description": "Name of the caller arranging the appointment, if different and known."},
            "visit_reason": {"type": "string", "description": "Visit reason explicitly collected from the patient."},
            "visit_reason_details": {"type": "string", "description": "Optional brief patient-described concern, in their own words."},
            "health_concern": {"type": "string", "description": "Caller-selected category from get_health_concerns."},
        },
        required=["booking_for", "phone_number", "doctor_id", "slot_id", "patient_name", "visit_reason", "health_concern"],
    ),
    FunctionSchema(
        name="cancel_appointment",
        description="Stage a real active appointment found for the confirmed phone number, repeat its doctor/date/time, and cancel only after explicit caller confirmation of those exact details.",
        properties={
            "phone_number": {"type": "string", "description": "Phone number confirmed during this voice session."},
            "appointment_id": {"type": "integer", "description": "ID returned by list_active_appointments."},
        },
        required=["phone_number", "appointment_id"],
    ),
    FunctionSchema(
        name="end_voice_session",
        description="After the caller clearly says goodbye, no thanks, or that they need nothing else, request a short spoken closing and end the call after it finishes.",
        properties={},
        required=[],
    ),
]
