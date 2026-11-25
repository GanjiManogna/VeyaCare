import re
from calendar import month_name
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from pipecat.services.llm_service import FunctionCallParams

from app.database import SessionLocal
from app.models import Appointment, Doctor, TimeSlot
from app.tools import check_doctor_availability, book_appointment, cancel_appointment
from app.phone_validation import is_valid_indian_mobile
from app.visit_reasons import VISIT_REASONS, visit_reasons_for
from app.health_concerns import HEALTH_CONCERNS, is_emergency_warning, extract_indian_mobile, redact_phone_numbers


_YES_RE = re.compile(
    r"(?:yes(?: it is| that is correct| that's correct| that is right| that's right| you(?: are|'re) correct(?: please confirm)?|"
    r" please confirm| please do| i confirm| i agree| i(?: am|'m) confirming(?: my)? appointment| go ahead| please| yes)?|"
    r"yeah(?: that is correct| that's correct| please| go ahead)?|yep(?: please| go ahead)?|"
    r"sure(?: please| go ahead)?|okay(?: please| go ahead)?|ok(?:ay)?(?: please| go ahead)?|"
    r"correct|that's correct|that is correct|that's right|that is right|i confirm(?: the appointment)?|"
    r"i agree|please do|please confirm|go ahead|haan(?: ji)?|han(?: ji)?|ji haan|ji han|bilkul)",
    re.IGNORECASE,
)
_NO_RE = re.compile(r"\b(?:no|nope|wrong|incorrect|not correct|not right|don't|do not|wait|stop)\b", re.IGNORECASE)
_PHONE_CORRECTION_RE = re.compile(
    r"\b(?:wrong|incorrect|not correct|not right|different|replace|change|correction)\b.{0,30}\b(?:phone|mobile|number|digits)\b|"
    r"\b(?:phone|mobile|number|digits)\b.{0,30}\b(?:wrong|incorrect|not correct|not right|different|replace|change)\b",
    re.IGNORECASE,
)
_CONNECTION_CHECK_RE = re.compile(r"\b(?:is this call connected|are we connected|can you hear me|can you hear us|are you there|are you listening|is the call connected)\b", re.IGNORECASE)
_PAUSE_OR_REPEAT_RE = re.compile(r"\b(?:wait|hold on|one moment|give me a moment|repeat that|say that again|could you repeat|can you repeat)\b", re.IGNORECASE)
_MONTHS = {name.casefold(): number for number, name in enumerate(month_name) if name}
_MONTHS.update({name[:3].casefold(): number for number, name in enumerate(month_name) if name})
_SPECIALITY_ALIAS_GROUPS = {
    "dermatology": ("dermatology", "dermatologist"),
}
_CLOSING_RE = re.compile(
    r"(?:no thank you|no thanks|that's all|that is all|nothing else|all done|goodbye|bye|"
    r"thank you goodbye|thanks goodbye|thank you that's all|thanks that's all|that's all thank you|that is all thank you|that's all thanks|that is all thanks)",
    re.IGNORECASE,
)
_SELF_BOOKING_RE = re.compile(r"\b(?:myself|for me|for myself|just me|self)\b", re.IGNORECASE)
_OTHER_BOOKING_RE = re.compile(
    r"\b(?:someone else|somebody else|another person|for my (?:\w+)|my (?:mother|father|mum|mom|dad|parent|wife|husband|spouse|son|daughter|child|brother|sister|friend|relative))\b",
    re.IGNORECASE,
)
_HEALTH_CONCERN_TERMS = {
    "Fever": ("fever", "temperature"),
    "Headache": ("headache", "migraine"),
    "Cough or cold": ("cough", "cold", "runny nose", "sore throat"),
    "Stomach pain": ("stomach", "tummy", "abdominal", "belly pain"),
    "Skin concern or rash": ("skin", "rash", "acne", "itch"),
    "Menstrual concern": ("period", "menstrual", "cycle"),
    "Joint or back pain": ("joint", "back pain", "knee pain", "shoulder pain"),
    "Eye concern": ("eye", "vision", "sight"),
    "Ear, nose, or throat concern": ("ear", "nose", "sinus", "throat", "voice"),
    "Child health concern": ("child", "baby", "son", "daughter", "pediatric"),
    "Routine check-up": ("routine", "check-up", "check up", "wellness"),
}


def is_explicit_confirmation(text: str) -> bool:
    """Accept a clear affirmative answer, never an LLM-supplied confirmation flag."""
    normalized = re.sub(r"[^\w\s']", " ", text.strip().lower())
    normalized = " ".join(normalized.split())
    return bool(normalized and not _NO_RE.search(normalized) and _YES_RE.fullmatch(normalized))


def india_today():
    # India uses a fixed UTC+05:30 offset, so this avoids a system tzdata
    # dependency while preserving the Asia/Kolkata calendar date on Windows.
    india = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
    return datetime.now(india).date()


def has_natural_date(text):
    value = str(text or "").casefold()
    month_pattern = "|".join(sorted(_MONTHS, key=len, reverse=True))
    return bool(
        re.search(r"\b(?:today|tomorrow|day after tomorrow)\b", value)
        or re.search(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{month_pattern})\b", value)
        or re.search(rf"\b(?:{month_pattern})\s+\d{{1,2}}(?:st|nd|rd|th)?\b", value)
        or re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
    )


def resolve_appointment_date(requested_date, caller_text="", today=None):
    """Resolve caller-relative dates against the server's Asia/Kolkata date."""
    local_today = today or india_today()
    normalized_text = str(caller_text or "").casefold()
    date_text = normalized_text or str(requested_date or "").casefold()
    caller_iso = re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized_text)
    if caller_iso:
        try:
            return date.fromisoformat(caller_iso.group()).isoformat()
        except ValueError:
            pass
    relative = None
    if re.search(r"\bday after tomorrow\b", date_text):
        relative = local_today + timedelta(days=2)
    elif re.search(r"\btomorrow\b", date_text):
        relative = local_today + timedelta(days=1)
    elif re.search(r"\btoday\b", date_text):
        relative = local_today

    month_pattern = "|".join(sorted(_MONTHS, key=len, reverse=True))
    day_first = re.search(
        rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{month_pattern})\b(?:[, ]+(?P<year>\d{{4}}))?",
        date_text,
    )
    month_first = re.search(
        rf"\b(?P<month>{month_pattern})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:[, ]+(?P<year>\d{{4}}))?\b",
        date_text,
    )
    explicit = day_first or month_first
    if explicit:
        try:
            month = _MONTHS[explicit.group("month")]
            day = int(explicit.group("day"))
            year_text = explicit.groupdict().get("year")
            if year_text:
                return date(int(year_text), month, day).isoformat()
            if relative:
                if (relative.month, relative.day) == (month, day):
                    return relative.isoformat()
            year = local_today.year
            candidate = date(year, month, day)
            if candidate < local_today:
                candidate = date(year + 1, month, day)
            return candidate.isoformat()
        except ValueError:
            return relative.isoformat() if relative else None
    if relative:
        return relative.isoformat()

    # A caller may have explicitly supplied an ISO date; only use the model's
    # argument verbatim when no natural date was found in the transcript.
    try:
        return date.fromisoformat(str(requested_date)).isoformat()
    except (TypeError, ValueError):
        return None


def _canonical_speciality(value):
    """Map a known spoken/provider variant to the clinic's stored speciality."""
    normalized = " ".join(str(value or "").split())
    folded = normalized.casefold()
    for canonical, aliases in _SPECIALITY_ALIAS_GROUPS.items():
        if folded in aliases:
            return canonical.title()
    return normalized


def _speciality_was_requested(speciality, caller_text):
    """Keep the caller-grounding check while accepting known speciality aliases."""
    canonical = _canonical_speciality(speciality)
    phrases = _SPECIALITY_ALIAS_GROUPS.get(canonical.casefold(), (canonical.casefold(),))
    text = str(caller_text or "").casefold()
    return bool(canonical) and any(
        re.search(rf"\b{re.escape(phrase)}\b", text)
        for phrase in phrases
    )


def record_user_transcript(state: dict, text: str, is_confirmation=is_explicit_confirmation):
    """Advance the session's one-turn confirmation state from final STT text."""
    raw_text = str(text or "").strip()
    state["transcript_sequence"] = state.get("transcript_sequence", 0) + 1
    safe_text = redact_phone_numbers(raw_text)
    candidate = extract_indian_mobile(raw_text)
    state["phone_candidate"] = candidate
    state["phone_candidate_sequence"] = state["transcript_sequence"] if candidate else None
    state["latest_user_text"] = safe_text
    history = state.setdefault("caller_transcripts", [])
    history.append(safe_text)
    del history[:-20]
    state["last_action_result"] = None
    if is_emergency_warning(raw_text):
        state["emergency_detected"] = True
        state["selected_slot"] = None
    if state.get("confirmed_phone") and _PHONE_CORRECTION_RE.search(raw_text):
        state["confirmed_phone"] = None
        state["phone_confirmation_completed"] = False
        state["phone_confirmed_transcript_sequence"] = None
    pending = state.get("awaiting_confirmation")
    grant = state.get("confirmation_grant")

    if _CONNECTION_CHECK_RE.search(raw_text) or _PAUSE_OR_REPEAT_RE.search(raw_text):
        state["phone_confirmation_armed"] = False
        state["confirmation_armed_kind"] = None
        state["confirmation_grant"] = None
        return

    # A grant is valid for the next final caller utterance only. A newer
    # transcription consumes/revokes it before any subsequent LLM tool call.
    if grant:
        state["confirmation_grant"] = None

    if not pending:
        offered = state.get("last_offered_slots") or []
        explicit_matches = [
            item for item in offered
            if _name_mentioned(raw_text, item.get("doctor_name"))
            and _time_mentioned(raw_text, item.get("time"))
        ]
        if (
            is_confirmation(raw_text)
            and state.get("last_offer_transcript_sequence") == state["transcript_sequence"] - 1
            and len(offered) == 1
        ):
            state["selected_slot"] = offered[0]
            state["selected_slot_transcript_sequence"] = state["transcript_sequence"]
        elif len(explicit_matches) == 1:
            state["selected_slot"] = explicit_matches[0]
            state["selected_slot_transcript_sequence"] = state["transcript_sequence"]
        else:
            state["last_offered_slots"] = []
        return

    kind = pending["kind"]
    phone_prompt_armed = state.pop("phone_confirmation_armed", False)
    affirmative = is_confirmation(raw_text)
    if kind == "phone" and affirmative and not phone_prompt_armed:
        # Do not use an unsolicited/interrupted yes; retain this pending number
        # until the verification question has actually finished speaking.
        return
    state["awaiting_confirmation"] = None
    if affirmative:
        if kind == "phone":
            phone = pending["details"]
            state["confirmed_phone"] = phone
            state["pending_phone"] = None
            state["phone_confirmation_completed"] = True
            state["phone_confirmed_transcript_sequence"] = state["transcript_sequence"]
        state["confirmation_grant"] = {
            "kind": kind,
            "details": pending["details"],
            "transcript_sequence": state["transcript_sequence"],
            "after_sequence": pending["after_sequence"],
        }
        return

    # A caller's next utterance was not an affirmative answer. Invalidate the
    # staged operation so a later unrelated "yes" cannot approve stale details.
    state["confirmation_grant"] = None
    state[pending["state_key"]] = None


def _state(params):
    state = params.app_resources
    if not isinstance(state, dict):
        raise RuntimeError("Voice session state is unavailable")
    return state


def _stage_confirmation(state, kind, details, state_key):
    state["awaiting_confirmation"] = {
        "kind": kind,
        "details": details,
        "state_key": state_key,
        "after_sequence": state.get("transcript_sequence", 0),
    }
    state["confirmation_grant"] = None


def _matching_grant(state, kind, details):
    grant = state.get("confirmation_grant")
    return bool(
        grant
        and grant["kind"] == kind
        and grant["details"] == details
        and grant["transcript_sequence"] > grant["after_sequence"]
        and grant["transcript_sequence"] == state.get("transcript_sequence")
    )


async def _reply(params, result):
    # Pipecat's FunctionCallParams.result_callback broadcasts a
    # FunctionCallResultFrame. Awaiting it lets the assistant context aggregator
    # append the result and push the next LLMContextFrame back to Gemini.
    await params.result_callback(result)


async def check_availability_handler(params: FunctionCallParams):
    a = params.arguments
    state = _state(params)
    if state.get("emergency_detected"):
        await _reply(params, {"success": False, "code": "emergency_care", "message": "This may need urgent attention. Contact emergency services or go to the nearest emergency department now instead of arranging a routine appointment."})
        return
    if state.get("booking_for"):
        requested_speciality = _canonical_speciality(a.get("speciality"))
        caller_text = " ".join(state.get("caller_transcripts", [state.get("latest_user_text", "")])).casefold()
        if not requested_speciality or not _speciality_was_requested(requested_speciality, caller_text):
            await _reply(params, {"success": False, "message": "Ask which speciality the caller wants and use the speciality they actually named."})
            return
        state["speciality"] = requested_speciality
        a = {**a, "speciality": requested_speciality}
    utterances = state.get("caller_transcripts") or [state.get("latest_user_text", "")]
    relevant_date_text = next((utterance for utterance in reversed(utterances) if has_natural_date(utterance)), "")
    resolved_date = resolve_appointment_date(a.get("date"), relevant_date_text)
    db = SessionLocal()
    try:
        result = check_doctor_availability(db, a.get("speciality"), resolved_date)
    finally:
        db.close()
    state["available_slots"] = []
    state["available_doctors"] = []
    state["available_slot_details"] = []
    state["selected_slot"] = None
    state["last_offered_slots"] = []
    requested_name = a.get("doctor_name")
    if requested_name:
        requested_name = " ".join(str(requested_name).split())
        caller_text = " ".join(state.get("caller_transcripts", [state.get("latest_user_text", "")]))
        if not _name_mentioned(caller_text, requested_name):
            await _reply(params, {
                "success": False,
                "clarification_required": True,
                "message": "The requested doctor name was not clearly spoken by the caller. Ask them to repeat the doctor's full name; do not substitute a similar name.",
            })
            return
        match_status, matched_doctors = match_doctor_name(requested_name, result)
        if match_status != "exact":
            state["available_doctors"] = []
            await _reply(params, {
                "success": False,
                "clarification_required": True,
                "requested_doctor_name": requested_name,
                "similar_doctors": [doctor["doctor_name"] for doctor in matched_doctors],
                "message": "No exact available-doctor match was found. Ask the caller to clarify from the listed names; never silently choose a similar doctor.",
            })
            return
        result = matched_doctors
    state["available_doctors"] = [
        {"doctor_id": doctor["doctor_id"], "doctor_name": doctor["doctor_name"]}
        for doctor in result
    ]
    state["available_slots"] = [
        (doctor["doctor_id"], slot["slot_id"])
        for doctor in result
        for slot in doctor["available_slots"]
    ]
    state["available_slot_details"] = [
        {
            "doctor_id": doctor["doctor_id"],
            "doctor_name": doctor["doctor_name"],
            "speciality": doctor["speciality"],
            "experience": doctor["experience"],
            "consultation_fee": doctor["consultation_fee"],
            **slot,
        }
        for doctor in result
        for slot in doctor["available_slots"]
    ]
    await _reply(params, {"success": True, "resolved_date": resolved_date, "doctors": result})


def _normalize_doctor_name(value):
    words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    return " ".join(word for word in words if word not in {"dr", "doctor"})


def _name_mentioned(transcript, name):
    transcript_words = re.findall(r"[a-z0-9]+", str(transcript or "").casefold())
    name_words = _normalize_doctor_name(name).split()
    return bool(name_words) and any(
        transcript_words[index:index + len(name_words)] == name_words
        for index in range(len(transcript_words))
    )


def _time_mentioned(transcript, value):
    match = re.fullmatch(r"0?(\d{1,2}):(\d{2})\s*(AM|PM)", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return False
    hour, minute, meridiem = match.groups()
    alternatives = (
        rf"(?<!\d)0?{int(hour)}:{minute}\s*{meridiem}(?!\w)",
        rf"(?<!\d)0?{int(hour)}\s*{meridiem}(?!\w)",
    )
    return any(re.search(pattern, transcript, re.IGNORECASE) for pattern in alternatives)


async def select_appointment_slot_handler(params: FunctionCallParams):
    state = _state(params)
    if state.get("emergency_detected"):
        await _reply(params, {"success": False, "code": "emergency_care", "message": "Please seek urgent emergency care instead of selecting a routine slot."})
        return
    try:
        doctor_id = int(params.arguments["doctor_id"])
        slot_id = int(params.arguments["slot_id"])
    except (KeyError, TypeError, ValueError):
        await _reply(params, {"success": False, "message": "Choose an exact doctor and slot from the availability just offered."})
        return
    offered = state.get("last_offered_slots") or []
    selected = next((
        item for item in offered
        if item["doctor_id"] == doctor_id and item["slot_id"] == slot_id
    ), None)
    latest = state.get("latest_user_text", "").casefold()
    yes_selected_this_slot = (
        state.get("selected_slot") == selected
        and state.get("selected_slot_transcript_sequence") == state.get("transcript_sequence")
    )
    explicit = bool(
        selected
        and _name_mentioned(latest, selected["doctor_name"])
        and _time_mentioned(latest, selected["time"])
    )
    if not selected or not (yes_selected_this_slot or explicit):
        await _reply(params, {"success": False, "message": "The caller has not selected that exact offered doctor and time. If they only said yes to multiple options, ask which doctor and time they choose."})
        return
    state["selected_slot"] = selected
    state["selected_slot_transcript_sequence"] = state.get("transcript_sequence")
    state["last_offered_slots"] = []
    await _reply(params, {
        "success": True,
        "selected_slot": selected,
        "slot_selection_recorded": True,
        "slot_confirmation_required": False,
        "next_step": "The caller's selection already records their confirmation of this exact doctor, date and time. Do not read these details back or ask them to confirm this slot again now. Continue by collecting the patient's full name and health concern, then collect and confirm a fresh phone number for this call. Keep the separate final complete appointment summary and booking confirmation before booking.",
    })


def _contains_phrase(text, phrase):
    return bool(phrase and re.search(rf"(?<!\w){re.escape(phrase.casefold())}(?!\w)", text.casefold()))


def _health_concern_was_said(text, concern):
    terms = _HEALTH_CONCERN_TERMS.get(concern, (concern,))
    return any(_contains_phrase(text, term) for term in terms)


def match_doctor_name(requested_name, available_doctors):
    """Match an actual available doctor exactly, or return suggestions for clarification."""
    requested = _normalize_doctor_name(requested_name)
    if not requested:
        return "unmatched", []
    exact = [
        doctor for doctor in available_doctors
        if _normalize_doctor_name(doctor.get("doctor_name")) == requested
    ]
    if len(exact) == 1:
        return "exact", exact
    if exact:
        return "ambiguous", exact
    scored = [
        (SequenceMatcher(None, requested, _normalize_doctor_name(doctor.get("doctor_name"))).ratio(), doctor)
        for doctor in available_doctors
    ]
    suggestions = [doctor for score, doctor in sorted(scored, key=lambda item: item[0], reverse=True) if score >= 0.65]
    return ("similar" if suggestions else "unmatched"), suggestions


async def begin_booking_handler(params: FunctionCallParams):
    """Start a new booking and discard any phone confirmation from older work."""
    state = _state(params)
    if state.get("emergency_detected"):
        await _reply(params, {"success": False, "code": "emergency_care", "message": "This may need urgent attention. Contact emergency services or go to the nearest emergency department now instead of arranging a routine appointment."})
        return
    booking_for = params.arguments.get("booking_for")
    if booking_for not in ("self", "someone_else"):
        await _reply(params, {"success": False, "message": "Ask whether the booking is for the caller or someone else first."})
        return
    latest_answer = state.get("latest_user_text", "")
    caller_said_self = bool(_SELF_BOOKING_RE.search(latest_answer))
    caller_said_other = bool(_OTHER_BOOKING_RE.search(latest_answer))
    caller_choice = "self" if caller_said_self and not caller_said_other else "someone_else" if caller_said_other and not caller_said_self else None
    if caller_choice != booking_for:
        await _reply(params, {"success": False, "message": "The caller has not clearly said whether this is for them or someone else. Ask the question and wait for their answer before starting a booking."})
        return
    state["booking_for"] = booking_for
    # The caller display name is not proof of the patient's full name. Ask and
    # record the actual patient name even for a self booking.
    state["patient_name"] = None
    state["speciality"] = None
    state["visit_reason"] = None
    state["visit_reason_details"] = None
    state["health_concern"] = None
    state["health_concern_details"] = None
    state["pending_phone"] = None
    state["confirmed_phone"] = None
    state["pending_booking"] = None
    state["pending_cancellation"] = None
    state["phone_confirmation_armed"] = False
    state["phone_prompt_after_tts"] = False
    state["phone_confirmation_completed"] = False
    state["phone_confirmed_transcript_sequence"] = None
    state["available_slots"] = []
    state["available_doctors"] = []
    state["available_slot_details"] = []
    state["selected_slot"] = None
    state["last_offered_slots"] = []
    state["awaiting_confirmation"] = None
    state["confirmation_grant"] = None
    if booking_for == "self":
        next_step = "Ask for the preferred speciality and date, check real availability, and record the exact chosen slot before collecting patient details."
    else:
        next_step = "Ask for the preferred speciality and date, check real availability, and record the exact chosen slot before collecting the other patient's details."
    await _reply(params, {"success": True, "booking_for": booking_for, "patient_name": state["patient_name"], "answer_recorded": True, "do_not_ask_booking_for_again": True, "next_step": next_step + " The caller's answer is recorded; do not ask who the appointment is for again."})


async def set_patient_name_handler(params: FunctionCallParams):
    """Record the patient name after the caller has said who the booking is for."""
    state = _state(params)
    name = params.arguments.get("patient_name")
    if state.get("booking_for") not in ("self", "someone_else"):
        await _reply(params, {"success": False, "message": "First ask whether the booking is for the caller or someone else."})
        return
    if not state.get("selected_slot"):
        await _reply(params, {"success": False, "message": "First let the caller select the exact doctor and slot that were offered."})
        return
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        await _reply(params, {"success": False, "message": "Ask for the patient's full name before collecting a phone number."})
        return
    normalized = " ".join(name.split())
    transcript_words = re.findall(r"[\w']+", state.get("latest_user_text", "").casefold())
    name_words = re.findall(r"[\w']+", normalized.casefold())
    if not name_words or not any(transcript_words[index:index + len(name_words)] == name_words for index in range(len(transcript_words))):
        await _reply(params, {"success": False, "message": "The patient's full name was not present in the latest caller utterance. Ask for the name and record exactly what the caller says."})
        return
    state["patient_name"] = normalized
    await _reply(params, {"success": True, "patient_name": normalized, "next_step": "The patient's name is recorded; do not ask them to confirm it. Ask for their health concern category, call get_health_concerns, record the category they choose without an extra confirmation, then collect and confirm a fresh mobile number."})


async def get_visit_reason_options_handler(params: FunctionCallParams):
    state = _state(params)
    speciality = _canonical_speciality(params.arguments.get("speciality"))
    latest = state.get("latest_user_text", "").casefold()
    if not state.get("booking_for") or not state.get("patient_name"):
        await _reply(params, {"success": False, "message": "First establish who the booking is for and collect the patient's full name."})
        return
    if not speciality or not visit_reasons_for(speciality):
        await _reply(params, {"success": False, "message": "Ask which listed speciality the caller wants before offering visit reasons."})
        return
    speciality_phrase = speciality.casefold()
    aliases = {
        "Gynecology": ("gynecology", "gynaecology", "gynecologist", "gynaecologist"),
        "Dermatology": _SPECIALITY_ALIAS_GROUPS["dermatology"],
    }
    if not any(re.search(rf"\b{re.escape(phrase)}\b", latest) for phrase in aliases.get(speciality, (speciality_phrase,))):
        await _reply(params, {"success": False, "message": "The caller has not chosen that speciality. Ask their preferred speciality instead of inferring it."})
        return
    state["speciality"] = speciality
    state["visit_reason"] = None
    state["visit_reason_details"] = None
    await _reply(params, {
        "success": True,
        "speciality": speciality,
        "options": visit_reasons_for(speciality),
        "disclaimer": "These are visit reasons, not diagnoses. The caller may choose Other and describe only what they want the clinic to know.",
    })


async def set_visit_reason_handler(params: FunctionCallParams):
    state = _state(params)
    reason = " ".join(str(params.arguments.get("health_concern") or params.arguments.get("visit_reason") or "").split())
    details = " ".join(str(params.arguments.get("health_concern_details") or params.arguments.get("visit_reason_details") or "").split()) or None
    latest = state.get("latest_user_text", "").casefold()
    options = HEALTH_CONCERNS
    if not state.get("selected_slot") or not state.get("patient_name"):
        await _reply(params, {"success": False, "message": "Select the exact slot and collect the patient's name before recording a health concern."})
        return
    if reason not in options:
        await _reply(params, {"success": False, "message": "Use one of the visit reasons returned for this speciality or choose Other."})
        return
    selected_by_caller = _health_concern_was_said(latest, reason)
    detail_was_said = details is None or _contains_phrase(latest, details)
    if not selected_by_caller and (reason != "Other" or details is None) or not detail_was_said:
        await _reply(params, {"success": False, "message": "Ask the caller to choose a reason or describe it in their own words; do not infer a medical concern."})
        return
    if reason == "Other" and not details:
        await _reply(params, {"success": False, "message": "Ask for a short description when the caller selects Other."})
        return
    if len(details or "") > 500:
        await _reply(params, {"success": False, "message": "Keep the short health concern description to 500 characters or fewer."})
        return
    if is_emergency_warning(f"{reason} {details or ''}"):
        state["emergency_detected"] = True
        await _reply(params, {"success": False, "code": "emergency_care", "message": "This may need urgent attention. Contact emergency services or go to the nearest emergency department now instead of arranging a routine appointment."})
        return
    state["visit_reason"] = reason
    state["visit_reason_details"] = details
    state["health_concern"] = reason
    state["health_concern_details"] = details
    await _reply(params, {"success": True, "visit_reason": reason, "visit_reason_details": details, "health_concern": reason, "health_concern_details": details, "next_step": "The health concern is recorded; do not ask the patient to confirm it. Collect and confirm a fresh current-call phone number, then give one concise complete appointment summary and obtain final booking confirmation."})


async def get_health_concerns_handler(params: FunctionCallParams):
    state = _state(params)
    if not state.get("selected_slot"):
        await _reply(params, {"success": False, "message": "Select the exact available doctor and time before collecting the patient's health concern."})
        return
    await _reply(params, {
        "success": True,
        "options": HEALTH_CONCERNS,
        "disclaimer": "These are appointment-routing categories, not diagnoses. Do not recommend treatment.",
    })


async def set_health_concern_handler(params: FunctionCallParams):
    await set_visit_reason_handler(params)


async def list_active_appointments_handler(params: FunctionCallParams):
    state = _state(params)
    phone = state.get("confirmed_phone")
    if not phone:
        await _reply(params, {"success": False, "message": "Confirm the caller's phone number before looking up appointments."})
        return
    db = SessionLocal()
    try:
        appointments = (
            db.query(Appointment)
            .filter(Appointment.phone_number == phone, Appointment.status == "booked")
            .order_by(Appointment.id.desc())
            .all()
        )
        rows = [
            {
                "appointment_id": appointment.id,
                "doctor": appointment.doctor.name,
                "speciality": appointment.doctor.speciality,
                "patient_name": appointment.patient_name,
                "booked_by_name": appointment.booked_by_name,
                "date": appointment.slot.date,
                "time": appointment.slot.time,
            }
            for appointment in appointments
        ]
    finally:
        db.close()
    await _reply(params, {"success": True, "appointments": rows})


async def set_phone_handler(params: FunctionCallParams):
    state = _state(params)
    if state.get("emergency_detected"):
        await _reply(params, {"success": False, "code": "emergency_care", "message": "Please seek urgent emergency care now instead of continuing routine appointment intake."})
        return
    phone = state.get("phone_candidate") if state.get("phone_candidate_sequence") == state.get("transcript_sequence") else None
    state["phone_candidate"] = None
    state["phone_candidate_sequence"] = None
    if phone == state.get("confirmed_phone") and state.get("phone_confirmation_completed"):
        await _reply(params, {"success": True, "already_confirmed": True, "message": "This number was already explicitly confirmed during this call. Do not ask for confirmation again."})
        return
    # A fresh phone collection attempt invalidates prior phone/action state so
    # a stale confirmation cannot authorize a different or malformed number.
    state["pending_phone"] = None
    state["confirmed_phone"] = None
    state["pending_booking"] = None
    state["pending_cancellation"] = None
    state["awaiting_confirmation"] = None
    state["confirmation_grant"] = None
    state["phone_confirmation_armed"] = False
    state["phone_prompt_after_tts"] = False
    state["phone_confirmation_completed"] = False
    state["phone_confirmed_transcript_sequence"] = None
    if not is_valid_indian_mobile(phone):
        await _reply(params, {"success": False, "message": "Please politely ask again for exactly 10 digits, starting with 6, 7, 8, or 9. Do not change or omit any digits."})
        return
    state["pending_phone"] = phone
    _stage_confirmation(state, "phone", phone, "pending_phone")
    await _reply(params, {"success": True, "phone_suffix": phone[-4:], "message": "For privacy, say only that the number ends in the four digits supplied in phone_suffix, then ask whether that is correct. Do not repeat the full number. It is not confirmed yet."})


async def confirm_phone_handler(params: FunctionCallParams):
    state = _state(params)
    phone = state.get("pending_phone")
    if state.get("phone_confirmation_completed") and state.get("confirmed_phone"):
        state["phone_confirmation_completed"] = False
        state["confirmation_grant"] = None
        suffix = state["confirmed_phone"][-4:]
        await _reply(params, {"success": True, "phone_suffix": suffix, "message": "The phone number was explicitly confirmed by the caller and is ready for this call."})
        return
    if phone and _matching_grant(state, "phone", phone):
        state["confirmed_phone"] = phone
        state["pending_phone"] = None
        state["confirmation_grant"] = None
        await _reply(params, {"success": True, "message": "The phone number ending in the four digits already read back is confirmed for this call."})
    else:
        await _reply(params, {"success": False, "message": "The phone number is not confirmed. If the caller said no, ask them to repeat it, validate and read back only its last four digits, then wait for a fresh explicit yes. If no number is pending, ask for the number now."})


def _available_booking_details(db, doctor_id, slot_id):
    row = (
        db.query(Doctor, TimeSlot)
        .join(TimeSlot, TimeSlot.doctor_id == Doctor.id)
        .filter(
            Doctor.id == doctor_id,
            TimeSlot.id == slot_id,
            TimeSlot.status == "available",
        )
        .first()
    )
    if not row:
        return None
    doctor, slot = row
    return {
        "doctor_id": doctor.id,
        "doctor": doctor.name,
        "speciality": doctor.speciality,
        "slot_id": slot.id,
        "date": slot.date,
        "time": slot.time,
        "experience": doctor.experience,
        "consultation_fee": doctor.consultation_fee,
    }


async def book_handler(params: FunctionCallParams):
    state = _state(params)
    a = params.arguments
    phone = str(a.get("phone_number", ""))
    try:
        doctor_id, slot_id = int(a["doctor_id"]), int(a["slot_id"])
    except (KeyError, TypeError, ValueError):
        await _reply(params, {"success": False, "message": "Missing valid doctor or slot."})
        return
    patient_name = a.get("patient_name")
    booking_for = a.get("booking_for")
    if state.get("emergency_detected"):
        await _reply(params, {"success": False, "code": "emergency_care", "message": "This may need urgent attention. Contact emergency services or go to the nearest emergency department now instead of booking routinely."})
        return
    session_patient_name = state.get("patient_name")
    if booking_for not in ("self", "someone_else") or booking_for != state.get("booking_for"):
        await _reply(params, {"success": False, "message": "First ask who the appointment is for and record that choice."})
        return
    if not isinstance(session_patient_name, str) or not session_patient_name.strip():
        await _reply(params, {"success": False, "message": "Ask for the patient's full name before booking."})
        return
    if not isinstance(patient_name, str) or " ".join(patient_name.split()).casefold() != session_patient_name.casefold():
        await _reply(params, {"success": False, "message": "Use the patient name collected and recorded for this booking."})
        return
    selected_slot = state.get("selected_slot")
    if not selected_slot or (doctor_id, slot_id) != (selected_slot.get("doctor_id"), selected_slot.get("slot_id")):
        await _reply(params, {"success": False, "message": "Select and retain the exact doctor and slot offered to and chosen by the caller before booking."})
        return
    if not state.get("confirmed_phone") or phone != state["confirmed_phone"]:
        await _reply(params, {"success": False, "message": "No phone number has been collected and explicitly confirmed for this booking in the current call. Ask the patient to provide their 10-digit number now; never reuse a profile, appointment, or earlier-call number."})
        return
    if not state.get("phone_confirmation_completed") and not state.get("phone_confirmed_transcript_sequence"):
        await _reply(params, {"success": False, "message": "The patient phone number must be explicitly confirmed during this voice call before booking."})
        return
    visit_reason = state.get("visit_reason")
    visit_reason_details = state.get("visit_reason_details")
    if not visit_reason or a.get("visit_reason") != visit_reason:
        await _reply(params, {"success": False, "message": "Collect and use the visit reason the patient selected before booking."})
        return
    if a.get("visit_reason_details") and a.get("visit_reason_details") != visit_reason_details:
        await _reply(params, {"success": False, "message": "Use only the optional visit-reason detail recorded from the patient's own words."})
        return
    health_concern = state.get("health_concern")
    health_concern_details = state.get("health_concern_details")
    if not health_concern or a.get("health_concern", health_concern) != health_concern:
        await _reply(params, {"success": False, "message": "Collect and record one caller-selected health concern category before booking."})
        return
    if health_concern == "Other" and not health_concern_details:
        await _reply(params, {"success": False, "message": "Collect a short description when the patient selects Other."})
        return
    if (doctor_id, slot_id) not in state.get("available_slots", []):
        await _reply(params, {"success": False, "message": "That doctor and slot were not returned by the latest availability check. Check real availability again before booking."})
        return

    request = {
        "phone_number": phone,
        "doctor_id": doctor_id,
        "slot_id": slot_id,
        "patient_name": session_patient_name,
        # A saved display label is only for greeting; it is not caller or
        # patient identity and must not be written into appointment records.
        "booked_by_name": state.get("booked_by_name") or None,
        "visit_reason": visit_reason,
        "visit_reason_details": visit_reason_details,
        "health_concern": health_concern,
        "health_concern_details": health_concern_details,
    }
    db = SessionLocal()
    try:
        slot_details = _available_booking_details(db, doctor_id, slot_id)
        if not slot_details:
            state["pending_booking"] = None
            state["awaiting_confirmation"] = None
            state["confirmation_grant"] = None
            await _reply(params, {"success": False, "message": "That doctor and slot are not currently available. Check availability again."})
            return

        staged = {"request": request, "slot_details": slot_details}
        if state.get("pending_booking") != staged or not _matching_grant(state, "booking", staged):
            state["pending_booking"] = staged
            _stage_confirmation(state, "booking", staged, "pending_booking")
            await _reply(params, {
                "success": False,
                "confirmation_required": True,
                "doctor": slot_details,
                "patient_name": request["patient_name"],
                "booked_by_name": request["booked_by_name"],
                "visit_reason": request["visit_reason"],
                "health_concern": health_concern,
                "consultation_fee": slot_details["consultation_fee"],
                "phone_suffix": phone[-4:],
                "message": "Booking not made. Repeat the patient's name, selected visit reason, doctor, date, time, and consultation fee; mention only the last four phone digits. Ask for explicit final confirmation, then retry with the same details.",
            })
            return

        # Consume before any await/DB mutation so a duplicate tool call cannot
        # reuse the same caller utterance as authorization.
        state["pending_booking"] = None
        state["awaiting_confirmation"] = None
        state["confirmation_grant"] = None
        result = book_appointment(
            db,
            phone,
            doctor_id,
            slot_id,
            request["patient_name"],
            request["booked_by_name"],
            request["visit_reason"],
            request["visit_reason_details"],
            request["health_concern"],
            request["health_concern_details"],
        )
        if result.get("success"):
            state["last_action_result"] = {
                "type": "booking",
                "success": True,
                "patient_name": result.get("patient_name"),
                "booked_by_name": result.get("booked_by_name"),
                "doctor": result.get("doctor"),
                "date": result.get("date"),
                "time": result.get("time"),
                "appointment_reference": result.get("appointment_reference"),
                "checkin_code": result.get("checkin_code"),
            }
            state["last_action_phone"] = phone
            state["confirmed_phone"] = None
            state["booking_for"] = None
            state["patient_name"] = None
            notify = state.get("notify_booking_succeeded")
            if callable(notify):
                try:
                    notify(phone)
                except Exception:
                    # The committed booking remains authoritative. A transient
                    # data-channel failure must not turn it into a tool failure.
                    pass
    finally:
        db.close()
    if result.get("success"):
        # The LLM needs booking facts to answer conversationally, not the full
        # contact number. The browser receives the number only on the private
        # success data-channel callback below.
        result = {key: value for key, value in result.items() if key != "phone_number"}
    await _reply(params, result)


async def cancel_handler(params: FunctionCallParams):
    state = _state(params)
    phone = str(params.arguments.get("phone_number", ""))
    try:
        appointment_id = int(params.arguments["appointment_id"])
    except (KeyError, TypeError, ValueError):
        await _reply(params, {"success": False, "message": "Missing valid appointment ID."})
        return
    if not state.get("confirmed_phone") or phone != state["confirmed_phone"]:
        await _reply(params, {"success": False, "message": "Phone number is not confirmed for this call."})
        return

    db = SessionLocal()
    try:
        appointment = (
            db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.phone_number == phone,
                Appointment.status == "booked",
            )
            .first()
        )
        if not appointment:
            state["pending_cancellation"] = None
            state["awaiting_confirmation"] = None
            state["confirmation_grant"] = None
            await _reply(params, {"success": False, "message": "No active appointment found for those details."})
            return

        details = {
            "phone_number": phone,
            "appointment_id": appointment.id,
            "doctor": appointment.doctor.name,
            "date": appointment.slot.date,
            "time": appointment.slot.time,
        }
        grant_matches = _matching_grant(state, "cancellation", details)
        if state.get("pending_cancellation") != details or not grant_matches:
            state["pending_cancellation"] = details
            _stage_confirmation(state, "cancellation", details, "pending_cancellation")
            await _reply(params, {
                "success": False,
                "confirmation_required": True,
                "appointment": {k: details[k] for k in ("appointment_id", "doctor", "date", "time")},
                "message": "Cancellation not made. Repeat these appointment details, ask for an explicit yes, then retry with the same appointment ID.",
            })
            return

        state["pending_cancellation"] = None
        state["awaiting_confirmation"] = None
        state["confirmation_grant"] = None
        result = cancel_appointment(db, phone, appointment_id)
        if result.get("success"):
            state["last_action_result"] = {
                "type": "cancellation",
                "success": True,
                "doctor": details["doctor"],
                "date": details["date"],
                "time": details["time"],
            }
            state["last_action_phone"] = phone
    finally:
        db.close()
    if result.get("success"):
        result = {key: value for key, value in result.items() if key != "phone_number"}
    await _reply(params, result)


async def end_voice_session_handler(params: FunctionCallParams):
    """Request session end only for an explicit caller goodbye or close."""
    state = _state(params)
    normalized = re.sub(r"[^\w\s']", " ", state.get("latest_user_text", "").casefold())
    normalized = " ".join(normalized.split())
    if not _CLOSING_RE.fullmatch(normalized):
        await _reply(params, {"success": False, "message": "Do not end the call yet. Continue helping the caller."})
        return
    if state.get("awaiting_confirmation") or state.get("pending_booking") or state.get("pending_cancellation"):
        await _reply(params, {"success": False, "message": "Resolve or safely cancel the pending appointment action before ending the call."})
        return
    state["end_after_assistant_response"] = True
    await _reply(params, {"success": True, "message": "Say a brief, warm goodbye. The call will end after that response finishes speaking."})


def register_appointment_tools(llm):
    handlers = {
        "check_doctor_availability": check_availability_handler,
        "get_visit_reason_options": get_visit_reason_options_handler,
        "set_visit_reason": set_visit_reason_handler,
        "get_health_concerns": get_health_concerns_handler,
        "set_health_concern": set_health_concern_handler,
        "select_appointment_slot": select_appointment_slot_handler,
        "begin_booking": begin_booking_handler,
        "set_patient_name": set_patient_name_handler,
        "list_active_appointments": list_active_appointments_handler,
        "set_phone_number": set_phone_handler,
        "confirm_phone_number": confirm_phone_handler,
        "book_appointment": book_handler,
        "cancel_appointment": cancel_handler,
        "end_voice_session": end_voice_session_handler,
    }
    for name, handler in handlers.items():
        llm.register_function(name, handler)
