from datetime import datetime

from pydantic import BaseModel


class AppointmentSlot(BaseModel):
    """A single bookable slot, as returned by /api/voice/available-slots."""

    id: int
    service: str
    provider: str
    start_time: datetime
    duration_minutes: int
    price: float
    status: str

    model_config = {"from_attributes": True}


class BookAppointmentRequest(BaseModel):
    patient_id: str
    slot_id: int


class CancelAppointmentRequest(BaseModel):
    patient_id: str
    slot_id: int


class BookedAppointment(BaseModel):
    """Confirmed booking details, as returned by /api/voice/book."""

    id: int
    patient_id: str
    service: str
    provider: str
    start_time: datetime
    duration_minutes: int
    price: float
    status: str
