
from pydantic import BaseModel, Field, field_validator


class AvailabilityRequest(BaseModel):
    speciality: str | None = None
    date: str | None = None


class BookingRequest(BaseModel):
    phone_number: str = Field(pattern=r"^[6-9][0-9]{9}$", description="A 10-digit Indian mobile number")
    doctor_id: int
    slot_id: int
    patient_name: str | None = None
    booked_by_name: str | None = None
    visit_reason: str = Field(min_length=1, max_length=120)
    visit_reason_details: str | None = Field(default=None, max_length=500)
    health_concern: str = Field(min_length=1, max_length=80)
    health_concern_details: str | None = Field(default=None, max_length=500)

    @field_validator("patient_name")
    @classmethod
    def reject_blank_patient_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Patient name must not be blank")
        return value.strip() if value is not None else None

    @field_validator("visit_reason")
    @classmethod
    def reject_blank_visit_reason(cls, value):
        if not value.strip():
            raise ValueError("Choose a reason for the visit")
        return value.strip()

    @field_validator("visit_reason_details")
    @classmethod
    def normalize_visit_reason_details(cls, value):
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None

    @field_validator("health_concern")
    @classmethod
    def validate_health_concern(cls, value):
        from app.health_concerns import HEALTH_CONCERNS
        if value.strip() not in HEALTH_CONCERNS:
            raise ValueError("Choose a health concern from the clinic intake options")
        return value.strip()

    @field_validator("health_concern_details")
    @classmethod
    def normalize_health_concern_details(cls, value):
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None


class CancellationRequest(BaseModel):
    phone_number: str = Field(pattern=r"^[6-9][0-9]{9}$", description="A 10-digit Indian mobile number")
    appointment_id: int
