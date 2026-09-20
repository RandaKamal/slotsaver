"""Persists voice-captured scheduling intent, and runs Nemotron off the hot path.

Why the split: a single Nemotron extraction takes ~12s. Doing that inside the
request meant the voice agent sat silent mid-call waiting for it, and ElevenLabs
would abandon the tool call if the patient spoke again - which is exactly what
happened on our first real call. So the write is now immediate and the model
work happens in a background task.

Because nothing is waiting on that task, it can afford a second critique pass
over its own draft (see refine_preferences). The caller never pays for it.
"""

import datetime
import logging

from sqlalchemy.orm import Session

from app.agents.nemotron.preference_extractor import (
    diff_extractions,
    extract_preferences,
    refine_preferences,
)
from app.db.models.preference import PreferenceRecord
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def save_pending_record(
    db: Session, patient_id: str, raw_text: str, context: str | None = None
) -> PreferenceRecord:
    """Writes what the patient said immediately, before any model runs."""
    record = PreferenceRecord(
        patient_id=patient_id,
        raw_text=raw_text,
        context=context,
        status="pending",
        raw_extraction={},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _apply_extraction(record: PreferenceRecord, extracted: dict) -> None:
    record.hard_constraints = extracted.get("hard_constraints")
    record.soft_preferences = extracted.get("soft_preferences")
    record.expiry = extracted.get("valid_until")
    record.contact_preferences = extracted.get("contact_preference")
    record.notify_if_opens = bool(extracted.get("notify_if_opens"))
    record.requested_time = extracted.get("requested_time")
    record.raw_extraction = extracted


def run_extraction(record_id: int, refine: bool = True) -> None:
    """Background task: extract, optionally self-critique, then update the row.

    Opens its own session - the request's session is already closed by the time
    this runs. Never raises: a failure marks the row 'failed' and leaves the
    patient's original wording intact, which is the part we cannot regenerate.
    """
    db = SessionLocal()
    try:
        record = db.get(PreferenceRecord, record_id)
        if record is None:
            logger.warning("preference record %s vanished before extraction", record_id)
            return

        today = datetime.date.today()
        try:
            draft = extract_preferences(
                record.raw_text, record.patient_id, context=record.context, today=today
            )
            final, diff = draft, {}
            if refine:
                revised = refine_preferences(
                    record.raw_text, draft, context=record.context, today=today
                )
                diff = diff_extractions(draft, revised)
                final = revised

            _apply_extraction(record, final)
            record.refinement_diff = diff
            record.status = "extracted"
            if diff:
                logger.info("critique revised record %s: %s", record_id, list(diff))
        except Exception:
            logger.exception("extraction failed for record %s", record_id)
            record.status = "failed"

        db.commit()
    finally:
        db.close()
