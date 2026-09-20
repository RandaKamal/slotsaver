"""Persists the RecoveryPlan dicts Kevin's /api/recovery/* routes build, and
advances the accept/decline/timeout state machine on top of that persisted
state. No ranking/reasoning here - candidates arrive already ranked; this
only decides who the "current" offer belongs to and what happens next.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models.recovery import RecoveryPlanRecord
from app.services.appointment_service import book_slot


def save_recovery_plan(db: Session, plan: dict, slot_id: int, cancelled_by: str | None) -> RecoveryPlanRecord:
    ranked = plan.get("ranked_candidate_ids") or []
    # The top candidate is the first offer - record that from the start, so
    # the offer history is complete even before any /response call happens.
    candidate_statuses = dict(plan.get("candidate_statuses") or {})
    if ranked:
        candidate_statuses.setdefault(ranked[0], "offered")

    record = RecoveryPlanRecord(
        plan_id=plan["plan_id"],
        slot_id=slot_id,
        cancelled_by=cancelled_by,
        open_slot=plan.get("open_slot") or {},
        candidates=plan.get("candidates") or [],
        excluded=plan.get("excluded") or [],
        ranked_candidate_ids=ranked,
        current_candidate_index=plan.get("current_candidate_index", 0),
        stage=plan.get("stage", "NORMAL"),
        selected_incentive=plan.get("selected_incentive"),
        status=plan.get("status", "pending"),
        candidate_statuses=candidate_statuses,
        revenue_at_risk=plan.get("revenue_at_risk"),
        message=plan.get("message"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _to_dict(record: RecoveryPlanRecord) -> dict:
    return {
        "plan_id": record.plan_id,
        "open_slot": record.open_slot,
        "cancelled_by": record.cancelled_by,
        "candidates": record.candidates,
        "excluded": record.excluded,
        "ranked_candidate_ids": record.ranked_candidate_ids,
        "current_candidate_index": record.current_candidate_index,
        "stage": record.stage,
        "selected_incentive": record.selected_incentive,
        "status": record.status,
        "candidate_statuses": record.candidate_statuses,
        "revenue_at_risk": record.revenue_at_risk,
        "message": record.message,
    }


def get_recovery_plan_from_db(db: Session, plan_id: str) -> dict | None:
    """Reconstructs the same dict shape the in-memory store returns, so
    GET /api/recovery/{plan_id} can fall back here transparently."""

    record = db.query(RecoveryPlanRecord).filter_by(plan_id=plan_id).first()
    if record is None:
        return None
    return _to_dict(record)


def record_candidate_response(db: Session, plan_id: str, response: str) -> dict:
    """Advances a persisted plan's offer state machine. The DB row (not any
    in-memory dict) is the only source of truth read or written here.

    - "accepted": atomically books the slot for the current candidate via
      book_slot - the same guarded UPDATE used everywhere else in the app,
      so a second accept (or a walk-in booking) on the same slot can't win
      even if it races this one. Plan becomes "filled".
    - "declined" / "timeout": marks the current candidate's offer
      (declined/expired) and moves to the next ranked candidate, marking
      them "offered". No ranked candidates left -> plan becomes "exhausted".
    """
    record = db.query(RecoveryPlanRecord).filter_by(plan_id=plan_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="plan not found")

    if record.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"plan {plan_id} is not awaiting a response (status={record.status})",
        )

    ranked = record.ranked_candidate_ids or []
    idx = record.current_candidate_index
    if idx >= len(ranked):
        raise HTTPException(status_code=409, detail=f"plan {plan_id} has no current candidate")

    current_patient_id = ranked[idx]
    statuses = dict(record.candidate_statuses or {})

    if response == "accepted":
        # Raises 409 itself if the slot is somehow no longer available -
        # that error propagates as-is, and nothing below it runs.
        book_slot(db, current_patient_id, record.slot_id)
        statuses[current_patient_id] = "accepted"
        record.candidate_statuses = statuses
        record.status = "filled"

    elif response in ("declined", "timeout"):
        statuses[current_patient_id] = "declined" if response == "declined" else "expired"
        record.current_candidate_index = idx + 1
        if record.current_candidate_index >= len(ranked):
            record.status = "exhausted"
        else:
            next_patient_id = ranked[record.current_candidate_index]
            statuses.setdefault(next_patient_id, "offered")
        record.candidate_statuses = statuses

    else:
        raise HTTPException(status_code=422, detail=f"invalid response: {response!r}")

    db.commit()
    db.refresh(record)
    return _to_dict(record)
