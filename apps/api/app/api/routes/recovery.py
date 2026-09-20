from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.mock_store import PATIENTS, RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.ranker import rank_candidates
from app.core.business_policy import get_business_policy
from app.db.models.appointment import Appointment
from app.db.session import get_db
from app.services.appointment_service import cancel_appointment
from app.services.recovery_service import (
    apply_incentive_decision,
    get_latest_plan_for_slot,
    get_recovery_plan_from_db,
    plan_record_to_dict,
    record_candidate_response,
)
from app.services.slot_recovery import run_recovery

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


@router.get("/by-slot/{slot_id}")
def get_recovery_plan_for_slot(slot_id: int, db: Session = Depends(get_db)) -> dict:
    """The most recent recovery plan for this slot, however it was created -
    a button click, a live-call cancellation, or the autonomous scheduler.

    This is how the live calendar/status-bar polling discovers a plan it
    never itself triggered. 404 means no cancellation has been processed for
    this slot yet (the scheduler ticks every few seconds, so on a freshly
    cancelled slot this can briefly 404 before a plan exists).
    """
    record = get_latest_plan_for_slot(db, slot_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No recovery plan for slot {slot_id}")
    return plan_record_to_dict(record)


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
def record_response(
    plan_id: str, payload: ResponseRequest, db: Session = Depends(get_db)
) -> dict:
    """Advances the offer to the plan's current candidate.

    The DB row is the only source of truth here (not RECOVERY_PLANS) - see
    recovery_service.record_candidate_response for the actual state machine:
    accept atomically books the slot (via the same guarded update booking
    already uses elsewhere, so it can't be double-won), decline/timeout move
    to the next ranked candidate. Requires a plan created via
    /from-cancellation - the /plan testing endpoint above never persists to
    the DB, so it has no slot to book against.
    """
    plan = record_candidate_response(db, plan_id, payload.response)
    if plan_id in RECOVERY_PLANS:
        RECOVERY_PLANS[plan_id] = plan
    return plan


@router.post("/{plan_id}/incentive")
def apply_incentive(plan_id: str, db: Session = Depends(get_db)) -> dict:
    """Incentive fallback: only reachable once the normal queue is exhausted.

    See recovery_service.apply_incentive_decision - calls Kevin's existing
    decide_incentive (never reimplemented), then deterministically checks the
    result against business policy before accepting it. From there, the same
    /response endpoint above handles accept (books the slot, plan filled) and
    decline (advances to the next ranked candidate) exactly as in the normal
    queue - nothing new to reimplement there.
    """
    plan = apply_incentive_decision(db, plan_id, get_business_policy(db))
    if plan_id in RECOVERY_PLANS:
        RECOVERY_PLANS[plan_id] = plan
    return plan


class CancellationRequest(BaseModel):
    slot_id: int


@router.post("/from-cancellation")
def recover_from_cancellation(
    payload: CancellationRequest, db: Session = Depends(get_db)
) -> dict:
    """Ensures a slot is free and has a recovery plan, synchronously.

    Cancels the booking if it's still booked (deterministic - see
    appointment_service.cancel_appointment). If it's already available - the
    normal case now that the autonomous scheduler cancels+plans on its own -
    this just proceeds to run_recovery, which is itself idempotent: given a
    slot that already has a plan for its current cancellation, it returns
    that plan rather than re-ranking. So this button is safe to click at any
    point in an already-running recovery; it never creates a second plan.

    Selects patients whose STORED INTENT fits the slot (deterministic, see
    recovery_matcher), then has Nemotron rank the survivors. Without stored
    intent this slot simply goes empty - nobody knows who to call. If Nemotron
    itself is unreachable (e.g. no NVIDIA_API_KEY), everything up to that
    point already happened and is persisted - only the ranking step is
    marked failed, never faked.

    Shares one pipeline with a patient cancelling on a live call
    (POST /api/voice/cancel) and with the autonomous scheduler; this is the
    one synchronous entry point, for when the dashboard wants the ranking
    back immediately instead of polling for it.
    """
    existing = db.get(Appointment, payload.slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {payload.slot_id}")

    if existing.status == "booked":
        slot = cancel_appointment(db, payload.slot_id)
    else:
        slot = existing

    return {**run_recovery(db, slot, cancelled_by=slot.last_cancelled_by), "cancelled_by": slot.last_cancelled_by}
