"""Patient-selected visit reasons. These are not diagnoses."""

VISIT_REASONS = {
    "Cardiology": ["Chest discomfort", "Heart or blood pressure check", "Palpitations", "Follow-up", "Other"],
    "Dermatology": ["Acne", "Skin allergy or irritation", "Hair fall", "Pigmentation", "Other"],
    "General Medicine": ["Fever or infection symptoms", "Digestive concern", "General health check", "Follow-up", "Other"],
    "Orthopedics": ["Joint pain", "Back or neck pain", "Injury", "Mobility concern", "Other"],
    "Neurology": ["Headache or migraine", "Numbness or tingling", "Sleep or memory concern", "Follow-up", "Other"],
    "Pediatrics": ["Child wellness check", "Fever or illness", "Growth or development question", "Follow-up", "Other"],
    "Gynecology": ["Irregular periods", "Menstrual pain", "Pregnancy-related consultation", "PCOS-related concerns", "Menopause-related concerns", "Other"],
    "ENT": ["Ear concern", "Nose or sinus concern", "Throat or voice concern", "Hearing concern", "Other"],
    "Ophthalmology": ["Vision check", "Eye irritation", "Eye pain", "Follow-up", "Other"],
    "Dentistry": ["Tooth pain", "Cleaning or check-up", "Gum concern", "Dental injury", "Other"],
}


def visit_reasons_for(speciality):
    return VISIT_REASONS.get(speciality, [])
