"""What the voice agent should already know about a patient before it calls them.

SlotSaver's whole premise is that intent is remembered. That is worth nothing
on a call if the agent starts from zero, so this renders everything stored for
a patient into a short brief the agent can actually use mid-conversation.

Kept deliberately compact: this goes into a system prompt on a live call, not
a report. Most recent first, capped, and always in the patient's own words
alongside the structured reading of them.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.outreach import OutreachAttempt
from app.db.models.preference import PreferenceRecord

_MAX_QUOTES = 3


def _humanise(record: PreferenceRecord) -> list[str]:
    """Structured preferences as short readable lines."""
    lines: list[str] = []
    soft = record.soft_preferences or {}
    hard = record.hard_constraints or {}

    if record.requested_time:
        lines.append(f"asks for {record.requested_time}")
    if soft.get("preferred_time_ranges"):
        lines.append("prefers " + ", ".join(soft["preferred_time_ranges"]))
    if soft.get("preferred_provider"):
        flexible = soft.get("provider_flexible", True)
        lines.append(
            f"wants {soft['preferred_provider']}"
            + ("" if flexible else " and will not switch")
        )
    if hard.get("excluded_days"):
        excluded = hard["excluded_days"]
        # Six exclusions means "only one day works" - say it that way round.
        if len(excluded) >= 5:
            allowed = [
                d
                for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
                if d not in excluded
            ]
            lines.append("only available " + ", ".join(allowed))
        else:
            lines.append("cannot do " + ", ".join(excluded))
    if hard.get("excluded_providers"):
        lines.append("will not see " + ", ".join(hard["excluded_providers"]))
    if record.expiry:
        lines.append(f"request expires {record.expiry}")
    return lines


def build_patient_brief(db: Session, patient_id: str) -> str:
    """A compact 'here is what we already know' block for the call prompt."""
    records = list(
        db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.patient_id == patient_id)
            .where(PreferenceRecord.status == "extracted")
            .order_by(PreferenceRecord.created_at.desc())
        ).scalars()
    )
    if not records:
        return "No previous conversations on file for this patient."

    parts: list[str] = []
    latest = records[0]

    summary = _humanise(latest)
    if summary:
        parts.append("Current preferences: " + "; ".join(summary) + ".")

    quotes = []
    for r in records[:_MAX_QUOTES]:
        when = r.created_at.strftime("%d %b") if r.created_at else "previously"
        quotes.append(f'  - On {when} they said: "{r.raw_text.strip()}"')
    if quotes:
        parts.append("In their own words (most recent first):\n" + "\n".join(quotes))

    if len(records) > 1:
        parts.append(f"({len(records)} saved conversations in total.)")

    # Prior contact matters: do not act like this is the first time we've called.
    prior = list(
        db.execute(
            select(OutreachAttempt)
            .where(OutreachAttempt.patient_id == patient_id)
            .where(OutreachAttempt.status.in_(("placed", "approved")))
            .order_by(OutreachAttempt.created_at.desc())
        ).scalars()
    )
    if len(prior) > 1:  # the current attempt is already in this list
        last = prior[1]
        when = last.created_at.strftime("%d %b") if last.created_at else "recently"
        parts.append(f"We last called this patient on {when}. Do not imply this is the first contact.")

    return "\n".join(parts)


def summarise_for_log(db: Session, patient_id: str) -> dict:
    """Same data, structured - handy for the dashboard and for debugging."""
    records = list(
        db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.patient_id == patient_id)
            .order_by(PreferenceRecord.created_at.desc())
        ).scalars()
    )
    return {
        "patient_id": patient_id,
        "saved_conversations": len(records),
        "latest_said": records[0].raw_text if records else None,
        "latest_at": records[0].created_at.isoformat() if records and records[0].created_at else None,
        "brief": build_patient_brief(db, patient_id),
    }
