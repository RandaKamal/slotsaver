"""Read endpoints backing the clinic dashboard and calendar."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.db.models.preference import PreferenceRecord
from app.db.session import get_db
from app.schemas.appointment import AppointmentSlot

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
