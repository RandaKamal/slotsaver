"""Deterministic availability lookup and booking. No AI/Nemotron involved:
availability is exactly what's in the DB, and booking is a conditional
update guarded by an atomic WHERE clause.
"""

import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.services.business_profile_service import get_booking_rules, get_time_of_day_ranges

TimeOfDay = Literal["morning", "afternoon", "evening"]


def get_available_slots(
    db: Session,
    provider: str | None = None,
    service: str | None = None,
    date: datetime.date | None = None,
    time_of_day: TimeOfDay | None = None,
) -> list[Appointment]:
    stmt = select(Appointment).where(Appointment.status == "available")

    if provider:
        stmt = stmt.where(Appointment.provider.ilike(f"%{provider}%"))
    if service:
        stmt = stmt.where(Appointment.service.ilike(f"%{service}%"))
    if date:
        day_start = datetime.datetime.combine(date, datetime.time.min)
        day_end = datetime.datetime.combine(date, datetime.time.max)
        stmt = stmt.where(Appointment.start_time.between(day_start, day_end))

    stmt = stmt.order_by(Appointment.start_time)
    results = list(db.execute(stmt).scalars().all())

    if time_of_day:
        lo, hi = get_time_of_day_ranges(db)[time_of_day]
        results = [a for a in results if lo <= a.start_time.hour < hi]

    rules = get_booking_rules(db)
    now = datetime.datetime.now()
    earliest = now + datetime.timedelta(minutes=rules["min_notice_minutes"])
    latest = now + datetime.timedelta(days=rules["max_horizon_days"])
    results = [a for a in results if earliest <= a.start_time <= latest]
    if not rules["same_day_allowed"]:
        results = [a for a in results if a.start_time.date() != now.date()]

    return results


def book_slot(db: Session, patient_id: str, slot_id: int) -> Appointment:
    """Atomically flips a slot from available -> booked.

    The WHERE clause (id AND status='available') is what makes this safe
    under concurrent requests: only one UPDATE can ever match a given row,
    so two simultaneous booking attempts on the same slot can't both win.
    """

    result = db.execute(
        update(Appointment)
        .where(Appointment.id == slot_id, Appointment.status == "available")
        .values(status="booked", customer_id=patient_id)
    )
    db.commit()

    if result.rowcount == 1:
        booked = db.get(Appointment, slot_id)
        assert booked is not None
        return booked

    existing = db.get(Appointment, slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {slot_id}")
    raise HTTPException(
        status_code=409,
        detail=f"Slot {slot_id} is no longer available (status={existing.status})",
    )


def cancel_appointment(db: Session, appointment_id: int) -> Appointment:
    """Clinic-side cancellation: staff or dashboard cancelling on anyone's behalf.

    Same WHERE-guarded pattern as book_slot: only an appointment currently
    'booked' can be cancelled, so cancelling an already-open or
    already-cancelled slot is rejected rather than silently accepted. The
    freed row is immediately what get_available_slots/book_slot see - this
    IS "making that time available for recovery," not a separate step.

    Deliberately does NOT check who holds the appointment; that is the point
    of a staff-side cancel. Patient-initiated cancellation goes through
    cancel_slot() below, which does check.
    """

    result = db.execute(
        update(Appointment)
        .where(Appointment.id == appointment_id, Appointment.status == "booked")
        # last_cancelled_by reads the row's own pre-update customer_id in the
        # same statement (standard SQL SET semantics) - no separate SELECT,
        # so the atomicity guarantee above is unchanged.
        .values(
            status="available",
            last_cancelled_by=Appointment.customer_id,
            customer_id=None,
            cancelled_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )
    db.commit()

    if result.rowcount == 1:
        cancelled = db.get(Appointment, appointment_id)
        assert cancelled is not None
        return cancelled

    existing = db.get(Appointment, appointment_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such appointment: {appointment_id}")
    raise HTTPException(
        status_code=409,
        detail=f"Appointment {appointment_id} is not booked (status={existing.status})",
    )


def cancel_slot(db: Session, patient_id: str, slot_id: int) -> Appointment:
    """Patient-side cancellation, used by the voice agent on a live call.

    Same atomicity as cancel_appointment, but the WHERE clause also pins the
    current holder, so a caller can only cancel their OWN appointment. Without
    that, anyone who reached the phone agent could cancel any slot id they
    guessed.
    """

    result = db.execute(
        update(Appointment)
        .where(
            Appointment.id == slot_id,
            Appointment.status == "booked",
            Appointment.customer_id == patient_id,
        )
        .values(
            status="available",
            last_cancelled_by=Appointment.customer_id,
            customer_id=None,
            cancelled_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )
    db.commit()

    if result.rowcount == 1:
        cancelled = db.get(Appointment, slot_id)
        assert cancelled is not None
        return cancelled

    existing = db.get(Appointment, slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {slot_id}")
    if existing.status != "booked":
        raise HTTPException(
            status_code=409, detail=f"Slot {slot_id} is not booked (status={existing.status})"
        )
    raise HTTPException(
        status_code=403, detail=f"Slot {slot_id} is not booked by {patient_id}"
    )


def appointments_for(db: Session, patient_id: str) -> list[Appointment]:
    """This patient's upcoming booked appointments, soonest first."""
    stmt = (
        select(Appointment)
        .where(Appointment.customer_id == patient_id)
        .where(Appointment.status == "booked")
        .order_by(Appointment.start_time)
    )
    return list(db.execute(stmt).scalars().all())
