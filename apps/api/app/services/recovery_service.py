"""Persists the RecoveryPlan dicts Kevin's /api/recovery/* routes build, so
the from-cancellation flow isn't dependent only on the in-memory
RECOVERY_PLANS dict in app/agents/mock_store.py. No ranking/reasoning here -
this only stores and reads back whatever plan dict it's given.
"""

from sqlalchemy.orm import Session

from app.db.models.recovery import RecoveryPlanRecord


def save_recovery_plan(db: Session, plan: dict, slot_id: int, cancelled_by: str | None) -> RecoveryPlanRecord:
    record = RecoveryPlanRecord(
        plan_id=plan["plan_id"],
        slot_id=slot_id,
        cancelled_by=cancelled_by,
        open_slot=plan.get("open_slot") or {},
        candidates=plan.get("candidates") or [],
        excluded=plan.get("excluded") or [],
        ranked_candidate_ids=plan.get("ranked_candidate_ids") or [],
        current_candidate_index=plan.get("current_candidate_index", 0),
        stage=plan.get("stage", "NORMAL"),
        selected_incentive=plan.get("selected_incentive"),
        status=plan.get("status", "pending"),
        revenue_at_risk=plan.get("revenue_at_risk"),
        message=plan.get("message"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_recovery_plan_from_db(db: Session, plan_id: str) -> dict | None:
    """Reconstructs the same dict shape the in-memory store returns, so
    GET /api/recovery/{plan_id} can fall back here transparently."""

    record = db.query(RecoveryPlanRecord).filter_by(plan_id=plan_id).first()
    if record is None:
        return None
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
        "revenue_at_risk": record.revenue_at_risk,
        "message": record.message,
    }
