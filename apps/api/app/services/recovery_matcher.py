"""Turns stored scheduling intent into recovery candidates for a freed slot.

This is the join between the two halves of SlotSaver: the voice layer writes
what patients want, and this finds the ones a newly-open slot actually suits.

Eligibility here is deterministic and conservative - it only ever REMOVES
people who cannot or should not be contacted. Nemotron ranks whoever survives;
it never decides eligibility, so it can't talk its way past a hard constraint.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.db.models.preference import PreferenceRecord
from app.services.business_profile_service import get_time_of_day_ranges
from app.core.business_hours import time_of_day_for_hour

_WEEKDAY = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _excluded(record: PreferenceRecord, slot_start: datetime.datetime, provider: str) -> str | None:
    """Reason this patient is NOT eligible, or None if they are."""
    hard = record.hard_constraints or {}

    if _WEEKDAY[slot_start.weekday()] in (hard.get("excluded_days") or []):
        return f"{_WEEKDAY[slot_start.weekday()]} is excluded"

    if provider in (hard.get("excluded_providers") or []):
        return f"will not see {provider}"

    if record.expiry:
        try:
            if slot_start.date() > datetime.date.fromisoformat(record.expiry):
                return f"request expired {record.expiry}"
        except ValueError:
            pass  # unparseable expiry is treated as no expiry, not as ineligible

    soft = record.soft_preferences or {}
    wanted = soft.get("preferred_provider")
    if wanted and not soft.get("provider_flexible", True) and wanted.lower() != provider.lower():
        return f"insists on {wanted}"

    return None


def find_candidates(
    db: Session, slot_start: datetime.datetime, provider: str, exclude_slot_id: int | None = None
) -> tuple[list[dict], list[dict]]:
    """Returns (eligible candidates for the ranker, excluded patients with reasons).

    Only patients who asked to be told about openings are considered at all -
    contacting anyone else would be unsolicited. This deliberately does not
    distinguish "waiting for any opening" from "already booked, but this
    slot suits their stored preference better" - a patient with
    notify_if_opens=True is eligible either way. Each candidate is tagged
    with their current booking (if any) so accepting this offer can be
    treated as a MOVE (see slot_recovery.cascade_after_move): freeing their
    old slot instead of just filling this one, which is what lets one
    cancellation cascade into a calendar-wide rearrangement instead of a
    single swap.
    """
    records = list(
        db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.notify_if_opens.is_(True))
            .where(PreferenceRecord.status == "extracted")
            .order_by(PreferenceRecord.created_at.desc())
        ).scalars()
    )
    time_ranges = get_time_of_day_ranges(db)

    # One intent per patient: their most recent wins.
    latest: dict[str, PreferenceRecord] = {}
    for r in records:
        latest.setdefault(r.patient_id, r)

    current_bookings: dict[str, Appointment] = {}
    if latest:
        stmt = select(Appointment).where(
            Appointment.customer_id.in_(latest.keys()),
            Appointment.status == "booked",
        )
        if exclude_slot_id is not None:
            stmt = stmt.where(Appointment.id != exclude_slot_id)
        for appt in db.execute(stmt).scalars():
            current_bookings[appt.customer_id] = appt

    eligible: list[dict] = []
    excluded: list[dict] = []
    for record in latest.values():
        reason = _excluded(record, slot_start, provider)
        if reason:
            excluded.append({"patient_id": record.patient_id, "reason": reason})
            continue

        soft = dict(record.soft_preferences or {})
        current = current_bookings.get(record.patient_id)
        eligible.append(
            {
                "patient_id": record.patient_id,
                "phone_number": record.phone_number,
                "soft_preferences": soft,
                "earlier_if_possible": bool((record.raw_extraction or {}).get("earlier_if_possible")),
                "requested_time": record.requested_time,
                "slot_time_range": time_of_day_for_hour(slot_start.hour, time_ranges),
                "expires": record.expiry,
                "said": record.raw_text,
                "last_contacted_days_ago": None,
                "recent_declines": 0,
                "currently_booked_slot_id": current.id if current else None,
                "currently_booked_start": current.start_time.isoformat() if current else None,
            }
        )
    return eligible, excluded
