
from sqlalchemy import Column, Integer, String, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    speciality = Column(String, nullable=False)
    experience = Column(Integer, default=0)
    consultation_fee = Column(Integer, nullable=False, default=500)

    appointments = relationship("Appointment", back_populates="doctor")
    slots = relationship("TimeSlot", back_populates="doctor")


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    status = Column(String, default="available")

    doctor = relationship("Doctor", back_populates="slots")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (Index("uq_appointments_appointment_reference", "appointment_reference", unique=True),)

    id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String, nullable=True)
    booked_by_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    status = Column(String, default="booked")
    visit_reason = Column(String, nullable=True)
    visit_reason_details = Column(String, nullable=True)
    health_concern = Column(String, nullable=True)
    health_concern_details = Column(String, nullable=True)
    appointment_reference = Column(String, nullable=True)
    checkin_code = Column(String, nullable=True)

    doctor = relationship("Doctor", back_populates="appointments")
    slot = relationship("TimeSlot")
