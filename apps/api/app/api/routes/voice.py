import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models.preference import PreferenceRecord
from app.db.session import get_db
from app.schemas.appointment import AppointmentSlot, BookAppointmentRequest, BookedAppointment
from app.schemas.memory import PreferenceRecordResponse, VoicePreferenceRequest
from app.services.appointment_service import TimeOfDay, book_slot, get_available_slots
from app.services.preference_service import run_extraction, save_pending_record

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
