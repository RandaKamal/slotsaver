from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.mock_store import BUSINESS_POLICY, PATIENTS, RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.incentive import decide_incentive
from app.agents.nemotron.ranker import rank_candidates
from app.db.models.appointment import Appointment
from app.db.session import get_db
from app.services.appointment_service import cancel_appointment
from app.services.recovery_matcher import find_candidates
from app.services.recovery_service import get_recovery_plan_from_db, save_recovery_plan

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
def get_recovery_plan(plan_id: str, db: Session = Depends(get_db)) -> dict:
    plan = RECOVERY_PLANS.get(plan_id)
    if plan:
        return plan
    # Falls back to the DB so a plan survives past this process's lifetime -
    # /plan (the manual-testing endpoint above) only ever writes in-memory,
    # so this fallback only ever has something for from-cancellation plans.
    plan = get_recovery_plan_from_db(db, plan_id)
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

    Cancels the booking (deterministic - see appointment_service.cancel_appointment;
    rejects a slot that isn't actually booked), selects patients whose STORED
    INTENT fits it (deterministic, see recovery_matcher), then has Nemotron rank
    the survivors. Without stored intent this slot simply goes empty - nobody
    knows who to call. If Nemotron itself is unreachable (e.g. no NVIDIA_API_KEY),
    everything up to that point already happened and is persisted - only the
    ranking step is marked failed, never faked.
    """
    existing = db.get(Appointment, payload.slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {payload.slot_id}")
    previous_holder = existing.customer_id

    slot = cancel_appointment(db, payload.slot_id)

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

    plan_id = new_plan_id()
    try:
        ranking = rank_candidates(open_slot, eligible)
    except Exception as exc:
        # The deterministic work above (cancellation, eligibility) already
        # happened and is real; only ranking failed. Persist that plainly
        # instead of a raw 500 or - worse - inventing a ranking.
        plan = {
            "plan_id": plan_id,
            "open_slot": open_slot,
            "candidates": eligible,  # unranked - honestly labelled via status below
            "ranked_candidate_ids": [],
            "current_candidate_index": 0,
            "stage": "NORMAL",
            "selected_incentive": None,
            "status": "ranking_failed",
            "revenue_at_risk": slot.price,
            "message": f"Eligibility found {len(eligible)} candidate(s), but ranking failed: {exc}",
        }
        save_recovery_plan(db, plan, slot_id=slot.id, cancelled_by=previous_holder)
        RECOVERY_PLANS[plan_id] = plan
        return {**plan, "cancelled_by": previous_holder, "eligible": eligible, "excluded": excluded}

    plan = {
        "plan_id": plan_id,
        "open_slot": open_slot,
        "candidates": ranking["candidates"],
        "ranked_candidate_ids": ranking["ranked_candidate_ids"],
        "current_candidate_index": 0,
        "stage": "NORMAL",
        "selected_incentive": None,
        "status": "pending",
        "revenue_at_risk": slot.price,
    }
    RECOVERY_PLANS[plan_id] = plan
    save_recovery_plan(db, plan, slot_id=slot.id, cancelled_by=previous_holder)

    return {
        **plan,
        "cancelled_by": previous_holder,
        "eligible": eligible,
        "excluded": excluded,
        "revenue_at_risk": slot.price,
    }
