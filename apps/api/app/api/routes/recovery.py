from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.mock_store import PATIENTS, RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.ranker import rank_candidates
from app.core.business_policy import BUSINESS_POLICY
from app.db.models.appointment import Appointment
from app.db.session import get_db
from app.services.appointment_service import cancel_appointment
from app.services.recovery_service import (
    apply_incentive_decision,
    get_recovery_plan_from_db,
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
    plan = apply_incentive_decision(db, plan_id, BUSINESS_POLICY)
    if plan_id in RECOVERY_PLANS:
        RECOVERY_PLANS[plan_id] = plan
    return plan


class CancellationRequest(BaseModel):
    slot_id: int


@router.post("/from-cancellation")
def recover_from_cancellation(
    payload: CancellationRequest, db: Session = Depends(get_db)
) -> dict:
    """Frees a booked slot and runs recovery on it, synchronously.

    Cancels the booking (deterministic - see appointment_service.cancel_appointment;
    rejects a slot that isn't actually booked), selects patients whose STORED
    INTENT fits it (deterministic, see recovery_matcher), then has Nemotron rank
    the survivors. Without stored intent this slot simply goes empty - nobody
    knows who to call. If Nemotron itself is unreachable (e.g. no NVIDIA_API_KEY),
    everything up to that point already happened and is persisted - only the
    ranking step is marked failed, never faked.

    Shares one pipeline with a patient cancelling on a live call
    (POST /api/voice/cancel); that path runs it in the background because
    someone is on the phone, this one blocks so the dashboard gets the ranking
    back to display.
    """
    existing = db.get(Appointment, payload.slot_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No such slot: {payload.slot_id}")
    previous_holder = existing.customer_id

    slot = cancel_appointment(db, payload.slot_id)

    return {**run_recovery(db, slot, cancelled_by=previous_holder), "cancelled_by": previous_holder}
