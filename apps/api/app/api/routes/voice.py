import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models.preference import PreferenceRecord
from app.db.session import get_db
from app.schemas.appointment import (
    AppointmentSlot,
    BookAppointmentRequest,
    BookedAppointment,
    CancelAppointmentRequest,
)
from app.schemas.memory import PreferenceRecordResponse, VoicePreferenceRequest
from app.services.appointment_service import (
    TimeOfDay,
    appointments_for,
    book_slot,
    cancel_slot,
    get_available_slots,
)
from app.services.preference_service import run_extraction, save_pending_record
from app.services.slot_recovery import recover_freed_slot

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/preferences", response_model=PreferenceRecordResponse)
def save_scheduling_intent(
    payload: VoicePreferenceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PreferenceRecordResponse:
    """Called by the ElevenLabs `save_scheduling_intent` tool.

    Returns as soon as the patient's wording is safely stored. Nemotron runs
    afterwards in a background task, so the voice agent is never left waiting
    ~12s mid-call for a model response.
    """

    record = save_pending_record(db, payload.patient_id, payload.raw_text, payload.context)
    background_tasks.add_task(run_extraction, record.id)
    return PreferenceRecordResponse.model_validate(record)


@router.get("/preferences/{record_id}", response_model=PreferenceRecordResponse)
def get_scheduling_intent(
    record_id: int, db: Session = Depends(get_db)
) -> PreferenceRecordResponse:
    """Reads back one record, including whether extraction has finished yet."""

    record = db.get(PreferenceRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such preference record: {record_id}")
    return PreferenceRecordResponse.model_validate(record)


@router.get("/available-slots", response_model=list[AppointmentSlot])
def get_available_slots_route(
    provider: str | None = None,
    service: str | None = None,
    date: datetime.date | None = None,
    time_of_day: TimeOfDay | None = None,
    db: Session = Depends(get_db),
) -> list[AppointmentSlot]:
    """Called by the ElevenLabs `get_available_slots` tool.

    Returns only real open slots from the DB — never invents availability.
    """

    slots = get_available_slots(db, provider=provider, service=service, date=date, time_of_day=time_of_day)
    return [AppointmentSlot.model_validate(slot) for slot in slots]


@router.post("/book", response_model=BookedAppointment)
def book_appointment(
    payload: BookAppointmentRequest, db: Session = Depends(get_db)
) -> BookedAppointment:
    """Called by the ElevenLabs `book_appointment` tool.

    Atomically books the slot if (and only if) it's still available.
    """

    appointment = book_slot(db, payload.patient_id, payload.slot_id)
    return BookedAppointment(
        id=appointment.id,
        patient_id=appointment.customer_id,
        service=appointment.service,
        provider=appointment.provider,
        start_time=appointment.start_time,
        duration_minutes=appointment.duration_minutes,
        price=appointment.price,
        status=appointment.status,
    )


@router.get("/my-appointments", response_model=list[AppointmentSlot])
def my_appointments(
    patient_id: str, db: Session = Depends(get_db)
) -> list[AppointmentSlot]:
    """Called by the ElevenLabs `get_my_appointments_call` tool.

    The agent needs this before it can cancel anything - it has to know what
    the patient actually has booked rather than asking them for a slot id.
    """

    return [AppointmentSlot.model_validate(a) for a in appointments_for(db, patient_id)]


@router.post("/cancel")
def cancel_appointment(
    payload: CancelAppointmentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Called by the ElevenLabs `cancel_appointment_call` tool.

    This is the event the whole product exists to react to. Cancelling frees
    the slot and immediately kicks off recovery in the background: find who
    else wants it, rank them, and queue the best match for owner approval.

    Recovery runs as a background task because ranking plus the incentive and
    call-brief decisions take ~20-30s of model time, and the patient is on the
    phone waiting to hear "that's cancelled".
    """

    appointment = cancel_slot(db, payload.patient_id, payload.slot_id)
    background_tasks.add_task(recover_freed_slot, appointment.id)

    return {
        "cancelled": True,
        "slot_id": appointment.id,
        "provider": appointment.provider,
        "service": appointment.service,
        "start_time": appointment.start_time.isoformat(),
        "message": "Appointment cancelled. The clinic will try to offer this slot to another patient.",
    }
