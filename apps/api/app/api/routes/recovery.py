from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.mock_store import BUSINESS_POLICY, PATIENTS, RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.incentive import decide_incentive
from app.agents.nemotron.ranker import rank_candidates
from app.db.models.appointment import Appointment
from app.db.session import get_db
from app.services.outreach_service import evaluate_top_candidate
from app.services.recovery_matcher import find_candidates

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class PlanRequest(BaseModel):
    open_slot: dict
    candidate_ids: list[str] | None = None  # pick from mock_store presets
    candidates: list[dict] | None = None  # OR pass fully custom candidates for freeform testing


@router.post("/plan")
def create_recovery_plan(payload: PlanRequest) -> dict:
    if payload.candidates:
        candidates = payload.candidates
    else:
        candidate_ids = payload.candidate_ids or list(PATIENTS.keys())
        candidates = [PATIENTS[pid] for pid in candidate_ids if pid in PATIENTS]

    ranking = rank_candidates(payload.open_slot, candidates)

    plan_id = new_plan_id()
    plan = {
        "plan_id": plan_id,
        "open_slot": payload.open_slot,
        "candidates": ranking["candidates"],
        "ranked_candidate_ids": ranking["ranked_candidate_ids"],
        "current_candidate_index": 0,
        "stage": "NORMAL",
        "selected_incentive": None,
        "status": "pending",
    }
    RECOVERY_PLANS[plan_id] = plan
    return plan


@router.get("/{plan_id}")
def get_recovery_plan(plan_id: str) -> dict:
    plan = RECOVERY_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


class ResponseRequest(BaseModel):
    response: str  # "accepted" | "declined" | "timeout"


@router.post("/{plan_id}/response")
def record_response(plan_id: str, payload: ResponseRequest) -> dict:
    plan = RECOVERY_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    if payload.response == "accepted":
        plan["status"] = "filled"
        return plan

    plan["current_candidate_index"] += 1
    if plan["current_candidate_index"] >= len(plan["ranked_candidate_ids"]):
        plan["status"] = "exhausted"
    return plan


@router.post("/{plan_id}/incentive")
def apply_incentive(plan_id: str) -> dict:
    plan = RECOVERY_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")

    decision = decide_incentive(
        open_slot=plan["open_slot"],
        business_policy=BUSINESS_POLICY,
        decline_history=[{"patient_id": pid, "response": "declined"} for pid in plan["ranked_candidate_ids"]],
    )
    plan["stage"] = "INCENTIVE"
    plan["selected_incentive"] = decision
    plan["current_candidate_index"] = 0
    plan["status"] = "pending"
    return plan


class CancellationRequest(BaseModel):
    slot_id: int


@router.post("/from-cancellation")
def recover_from_cancellation(
    payload: CancellationRequest, db: Session = Depends(get_db)
) -> dict:
    """The whole product in one call: a booked slot frees up, and we find who wants it.

    Frees the slot, selects patients whose STORED INTENT fits it (deterministic,
    see recovery_matcher), then has Nemotron rank the survivors. Without stored
    intent this slot simply goes empty - nobody knows who to call.
    """
    slot = db.get(Appointment, payload.slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {payload.slot_id}")

    previous_holder = slot.customer_id
    slot.status = "available"
    slot.customer_id = None
    db.commit()
    db.refresh(slot)

    eligible, excluded = find_candidates(db, slot.start_time, slot.provider)

    open_slot = {
        "slot_id": slot.id,
        "provider": slot.provider,
        "service_type": slot.service,
        "start": slot.start_time.isoformat(),
        "duration_min": slot.duration_minutes,
        "price": slot.price,
    }

    if not eligible:
        return {
            "open_slot": open_slot,
            "cancelled_by": previous_holder,
            "eligible": [],
            "excluded": excluded,
            "plan_id": None,
            "revenue_at_risk": slot.price,
            "message": "No stored intent matches this slot - it would go unfilled.",
        }

    ranking = rank_candidates(open_slot, eligible)
    plan_id = new_plan_id()
    plan = {
        "plan_id": plan_id,
        "open_slot": open_slot,
        "candidates": ranking["candidates"],
        "ranked_candidate_ids": ranking["ranked_candidate_ids"],
        "current_candidate_index": 0,
        "stage": "NORMAL",
        "selected_incentive": None,
        "status": "pending",
    }
    RECOVERY_PLANS[plan_id] = plan

    # Ranking finds who could take this slot. This decides whether calling
    # the top match is actually worth doing, and if so, drafts the call.
    top_id = ranking["ranked_candidate_ids"][0]
    top_candidate = next(c for c in eligible if c["patient_id"] == top_id)
    top_score = next(c["match_score"] for c in ranking["candidates"] if c["patient_id"] == top_id)
    outreach = evaluate_top_candidate(db, open_slot, top_candidate, top_score, slot.price)

    return {
        **plan,
        "cancelled_by": previous_holder,
        "eligible": eligible,
        "excluded": excluded,
        "revenue_at_risk": slot.price,
        "outreach": {
            "id": outreach.id,
            "should_call": outreach.should_call,
            "reason": outreach.decision_reason,
            "incentive": outreach.incentive,
            "call_brief": outreach.call_brief,
            "status": outreach.status,
        },
    }
