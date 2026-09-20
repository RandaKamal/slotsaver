"""Read endpoints backing the clinic dashboard and calendar, plus cancellation."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.db.models.preference import PreferenceRecord
from app.db.session import get_db
from app.schemas.appointment import AppointmentSlot
from app.services.appointment_service import cancel_appointment

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentSlot])
def list_appointments(
    status: str | None = None, db: Session = Depends(get_db)
) -> list[AppointmentSlot]:
    """Every appointment the calendar draws - booked and available alike."""
    stmt = select(Appointment).order_by(Appointment.start_time)
    if status:
        stmt = stmt.where(Appointment.status == status)
    return [AppointmentSlot.model_validate(a) for a in db.execute(stmt).scalars()]


@router.post("/{appointment_id}/cancel", response_model=AppointmentSlot)
def cancel(appointment_id: int, db: Session = Depends(get_db)) -> AppointmentSlot:
    """Cancels a booked appointment, freeing that time for recovery.

    Deterministic only - no ranking here. To also find and rank patients for
    the freed slot in one call, use POST /api/recovery/from-cancellation,
    which calls this same service function internally.
    """
    appointment = cancel_appointment(db, appointment_id)
    return AppointmentSlot.model_validate(appointment)


@router.get("/metrics")
def dashboard_metrics(db: Session = Depends(get_db)) -> dict:
    """Counts behind the dashboard tiles. Real rows, not fixtures."""

    def count(stmt) -> int:
        return db.execute(stmt).scalar_one()

    open_slots = count(
        select(func.count()).select_from(Appointment).where(Appointment.status == "available")
    )
    booked = count(
        select(func.count()).select_from(Appointment).where(Appointment.status == "booked")
    )
    # Patients who asked to be told about openings and whose request still stands.
    waiting = count(
        select(func.count(func.distinct(PreferenceRecord.patient_id)))
        .where(PreferenceRecord.notify_if_opens.is_(True))
        .where(PreferenceRecord.status == "extracted")
    )
    revenue_at_risk = (
        db.execute(
            select(func.coalesce(func.sum(Appointment.price), 0.0)).where(
                Appointment.status == "available"
            )
        ).scalar_one()
        or 0.0
    )

    return {
        "open_slots": open_slots,
        "booked": booked,
        "patients_waiting": waiting,
        "revenue_at_risk": round(float(revenue_at_risk), 2),
    }
