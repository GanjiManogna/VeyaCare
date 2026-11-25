"""Patient-selected appointment routing concerns and emergency escalation."""

import re


HEALTH_CONCERNS = [
    "Fever",
    "Headache",
    "Cough or cold",
    "Stomach pain",
    "Skin concern or rash",
    "Menstrual concern",
    "Joint or back pain",
    "Eye concern",
    "Ear, nose, or throat concern",
    "Child health concern",
    "Routine check-up",
    "Other",
]

EMERGENCY_PATTERN = re.compile(
    r"\b(?:severe breathing difficulty|difficulty breathing|trouble breathing|"
    r"cannot breathe|can't breathe|chest pain|stroke symptoms?|face drooping|"
    r"slurred speech|sudden arm weakness|uncontrolled bleeding|heavy bleeding that won't stop|"
    r"loss of consciousness|lost consciousness|unconscious|not waking)\b",
    re.IGNORECASE,
)

_PHONE_SHAPE_PATTERN = re.compile(r"(?<!\d)([0-9](?:[\s.,()-]*[0-9]){9,10})(?!\d)")


def is_emergency_warning(text):
    value = str(text or "")
    for match in EMERGENCY_PATTERN.finditer(value):
        prefix = value[max(0, match.start() - 48):match.start()]
        if re.search(r"\b(?:no|not|without|denies|denied|don't|do not)\b(?:\W+\w+){0,4}\W*$", prefix, re.IGNORECASE):
            continue
        return True
    return False


def extract_indian_mobile(text):
    """Extract only a valid ASCII mobile value; caller text is never retained."""
    match = _PHONE_SHAPE_PATTERN.search(str(text or ""))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return digits if len(digits) == 10 and digits[0] in "6789" else None


def redact_phone_numbers(text):
    """Redact phone-shaped digit sequences before retaining or forwarding text."""
    return _PHONE_SHAPE_PATTERN.sub("[phone number provided]", str(text or ""))
