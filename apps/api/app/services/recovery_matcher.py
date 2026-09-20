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

from app.db.models.preference import PreferenceRecord

_WEEKDAY = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _time_range(hour: int) -> str:
    if hour < 12:
        return "morning"
    return "afternoon" if hour < 17 else "evening"


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
    db: Session, slot_start: datetime.datetime, provider: str
) -> tuple[list[dict], list[dict]]:
    """Returns (eligible candidates for the ranker, excluded patients with reasons).

    Only patients who asked to be told about openings are considered at all -
    contacting anyone else would be unsolicited.
    """
    records = list(
        db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.notify_if_opens.is_(True))
            .where(PreferenceRecord.status == "extracted")
            .order_by(PreferenceRecord.created_at.desc())
        ).scalars()
    )

    # One intent per patient: their most recent wins.
    latest: dict[str, PreferenceRecord] = {}
    for r in records:
        latest.setdefault(r.patient_id, r)

    eligible: list[dict] = []
    excluded: list[dict] = []
    for record in latest.values():
        reason = _excluded(record, slot_start, provider)
        if reason:
            excluded.append({"patient_id": record.patient_id, "reason": reason})
            continue

        soft = dict(record.soft_preferences or {})
        eligible.append(
            {
                "patient_id": record.patient_id,
                "phone_number": record.phone_number,
                "soft_preferences": soft,
                "earlier_if_possible": bool((record.raw_extraction or {}).get("earlier_if_possible")),
                "requested_time": record.requested_time,
                "slot_time_range": _time_range(slot_start.hour),
                "expires": record.expiry,
                "said": record.raw_text,
                "last_contacted_days_ago": None,
                "recent_declines": 0,
            }
        )
    return eligible, excluded
