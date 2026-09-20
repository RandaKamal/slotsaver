"""The owner-approval queue for outbound recovery calls.

Nemotron decides a call is worth making and drafts what the agent should
say. If the active business profile has opted into
recovery_rules.auto_call_enabled, the call already went out automatically
(see outreach_service.maybe_auto_call) and this queue is just a record of
that. Otherwise nothing dials until an owner approves the specific row here
via POST /{attempt_id}/approve.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.outreach import OutreachAttempt
from app.db.session import get_db
from app.services.outreach_service import place_call_for_attempt

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
        # Exposed so it is possible to tell from outside whether a placed call
        # can have its outcome read back at all - a null here means the queue
        # has nothing to advance on but the timeout.
        "conversation_id": a.conversation_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }


@router.get("/pending")
def list_pending(db: Session = Depends(get_db)) -> list[dict]:
    """Calls Nemotron thinks are worth making, awaiting an owner's decision.

    Only ever has rows when auto_call_enabled is off - an auto-placed call
    skips 'pending_approval' entirely (see maybe_auto_call), so this queue
    naturally empties out once a business turns full automation on.
    """
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
    # a normal and honest state, not an error. place_call_for_attempt leaves
    # status "approved" on CallNotConfigured, or sets "placed"/"failed".
    attempt = place_call_for_attempt(db, attempt)
    result = _serialize(attempt)
    if attempt.status not in ("placed",):
        result["call_error"] = f"call_status:{attempt.status}"
    return result


@router.post("/{attempt_id}/reject")
def reject(attempt_id: int, payload: DecisionRequest, db: Session = Depends(get_db)) -> dict:
    return _serialize(_mark(db, attempt_id, "rejected", payload))
