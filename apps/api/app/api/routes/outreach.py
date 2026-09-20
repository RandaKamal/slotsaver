"""The owner-approval queue for outbound recovery calls.

Nemotron decides a call is worth making and drafts what the agent should say;
nothing dials out until an owner approves the specific row here. Approving
does not yet place a call - place_call() is a stub until Twilio is wired
(see docs/twilio-integration.md) - but the row is marked 'approved' so the
dial-out step has exactly one well-defined trigger to attach to later.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.appointment import Appointment
from app.db.models.outreach import OutreachAttempt
from app.services.call_service import CallNotConfigured, place_call
from app.services.patient_memory import build_patient_brief
from app.db.session import get_db

router = APIRouter(prefix="/api/outreach", tags=["outreach"])
logger = logging.getLogger(__name__)


def _serialize(a: OutreachAttempt) -> dict:
    return {
        "id": a.id,
        "slot_id": a.slot_id,
        "patient_id": a.patient_id,
        "phone_number": a.phone_number,
        "match_score": a.match_score,
        "revenue_at_risk": a.revenue_at_risk,
        "should_call": a.should_call,
        "decision_reason": a.decision_reason,
        "incentive": a.incentive,
        "call_brief": a.call_brief,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }


@router.get("/pending")
def list_pending(db: Session = Depends(get_db)) -> list[dict]:
    """Calls Nemotron thinks are worth making, awaiting an owner's decision."""
    rows = db.execute(
        select(OutreachAttempt)
        .where(OutreachAttempt.status == "pending_approval")
        .where(OutreachAttempt.should_call.is_(True))
        .order_by(OutreachAttempt.created_at.desc())
    ).scalars()
    return [_serialize(r) for r in rows]


@router.get("/{attempt_id}")
def get_attempt(attempt_id: int, db: Session = Depends(get_db)) -> dict:
    attempt = db.get(OutreachAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail=f"No such outreach attempt: {attempt_id}")
    return _serialize(attempt)


class DecisionRequest(BaseModel):
    decided_by: str | None = None  # owner identity, once auth exists


def _mark(db: Session, attempt_id: int, status: str, payload: DecisionRequest) -> OutreachAttempt:
    import datetime

    attempt = db.get(OutreachAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail=f"No such outreach attempt: {attempt_id}")
    if attempt.status != "pending_approval":
        raise HTTPException(
            status_code=409, detail=f"Attempt {attempt_id} is already '{attempt.status}'"
        )
    attempt.status = status
    attempt.decided_by = payload.decided_by
    attempt.decided_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.post("/{attempt_id}/approve")
def approve(attempt_id: int, payload: DecisionRequest, db: Session = Depends(get_db)) -> dict:
    attempt = _mark(db, attempt_id, "approved", payload)

    # The approval itself always succeeds and is recorded regardless of
    # whether telephony is wired up yet - "approved, call not yet placed" is
    # a normal and honest state, not an error.
    slot_row = db.get(Appointment, attempt.slot_id)
    slot = (
        {
            "provider": slot_row.provider,
            "service_type": slot_row.service,
            "start": slot_row.start_time.strftime("%A %d %B at %I:%M %p"),
        }
        if slot_row
        else None
    )
    call_error: str | None = None
    try:
        place_call(attempt, slot, build_patient_brief(db, attempt.patient_id))
        attempt.status = "placed"
    except CallNotConfigured as exc:
        logger.info("attempt %s approved but not callable yet: %s", attempt_id, exc)
        call_error = f"not configured: {exc}"
    except Exception as exc:
        logger.exception("call placement failed for attempt %s", attempt_id)
        attempt.status = "failed"
        call_error = str(exc)
    db.commit()
    db.refresh(attempt)
    result = _serialize(attempt)
    # Surfaced here (not just logged) because this deployment's operator may
    # not have log access - a 500-line stack trace only in Render's own logs
    # is useless if nobody can open Render's logs mid-demo.
    if call_error:
        result["call_error"] = call_error
    return result


@router.post("/{attempt_id}/reject")
def reject(attempt_id: int, payload: DecisionRequest, db: Session = Depends(get_db)) -> dict:
    return _serialize(_mark(db, attempt_id, "rejected", payload))
