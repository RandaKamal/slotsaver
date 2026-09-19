from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.mock_store import BUSINESS_POLICY, PATIENTS, RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.incentive import decide_incentive
from app.agents.nemotron.ranker import rank_candidates

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
