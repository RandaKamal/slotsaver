"""Persists the RecoveryPlan dicts Kevin's /api/recovery/* routes build, and
advances the accept/decline/timeout state machine on top of that persisted
state. No ranking/reasoning here - candidates arrive already ranked; this
only decides who the "current" offer belongs to and what happens next.
"""

import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.nemotron.incentive import decide_incentive
from app.db.models.recovery import RecoveryPlanRecord
from app.services.appointment_service import book_slot


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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
        # A real offer window starts the moment the top candidate is queued -
        # this is what the autonomous scheduler compares against to fire a
        # real timeout instead of waiting on a click that may never come.
        current_offer_at=_utcnow() if ranked else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_latest_plan_for_slot(db: Session, slot_id: int) -> RecoveryPlanRecord | None:
    """Most recent plan for this slot, if any. Used both to let the frontend
    discover a plan it didn't itself trigger, and by run_recovery to avoid
    creating a second plan for a cancellation that's already being handled."""
    return (
        db.query(RecoveryPlanRecord)
        .filter_by(slot_id=slot_id)
        .order_by(RecoveryPlanRecord.created_at.desc())
        .first()
    )


def plan_record_to_dict(record: RecoveryPlanRecord) -> dict:
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
    return plan_record_to_dict(record)


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
        record.current_offer_at = None  # nothing left to time out
        db.commit()
        db.refresh(record)

        # Deferred import: slot_recovery.py imports FROM this module (it
        # calls save_recovery_plan/get_latest_plan_for_slot), so importing it
        # back at module load time would be circular. If this candidate was
        # already booked elsewhere, accepting this offer was a move, not a
        # plain fill - see cascade_after_move.
        from app.services.slot_recovery import cascade_after_move

        cascade_after_move(db, current_patient_id, record.slot_id)
        return plan_record_to_dict(record)

    elif response in ("declined", "timeout"):
        statuses[current_patient_id] = "declined" if response == "declined" else "expired"
        record.current_candidate_index = idx + 1
        if record.current_candidate_index >= len(ranked):
            record.status = "exhausted"
            record.current_offer_at = None
        else:
            next_patient_id = ranked[record.current_candidate_index]
            # Unconditional, not setdefault: a candidate re-offered during the
            # incentive round may already have "declined"/"expired" from the
            # earlier full-price round. Being offered again must overwrite
            # that stale status, not be suppressed by it (matches
            # apply_incentive_decision's own first-offer assignment below).
            statuses[next_patient_id] = "offered"
            record.current_offer_at = _utcnow()
        record.candidate_statuses = statuses

    else:
        raise HTTPException(status_code=422, detail=f"invalid response: {response!r}")

    db.commit()
    db.refresh(record)
    return plan_record_to_dict(record)


def _incentive_within_policy(
    decision: dict, business_policy: dict, slot_price: float, service: str
) -> tuple[bool, str | None]:
    """Deterministic backstop over Nemotron's incentive choice - mirrors the
    role recovery_matcher.find_candidates plays for ranking: the model picks,
    this gates. The prompt already tells it these rules; this is what makes
    them actually enforced rather than merely requested.
    """
    if decision.get("decision") != "offer_incentive":
        return True, None  # nothing to validate for continue/stop decisions

    chosen_id = decision.get("chosen_incentive")
    allowed = {i["id"]: i for i in business_policy.get("allowed_incentives", [])}
    if chosen_id not in allowed:
        return False, f"chosen incentive {chosen_id!r} is not in the approved list"

    if service in business_policy.get("excluded_services", []):
        return False, f"{service!r} is excluded from incentives by policy"

    incentive = allowed[chosen_id]
    if incentive.get("type") == "percent_discount":
        max_pct = business_policy.get("max_discount_percent", 0)
        if incentive.get("value", 0) > max_pct:
            return False, f"{incentive['value']}% exceeds the {max_pct}% policy maximum"
        discounted = slot_price * (1 - incentive["value"] / 100)
        min_revenue = business_policy.get("minimum_revenue", 0)
        if discounted < min_revenue:
            return False, f"discounted price {discounted:.2f} is below the {min_revenue} minimum"

    return True, None


def apply_incentive_decision(db: Session, plan_id: str, business_policy: dict) -> dict:
    """Incentive fallback: only reachable once the normal queue is exhausted.

    Calls Kevin's decide_incentive (never invented/mocked here), validates
    whatever it returns against business_policy deterministically, and only
    if it chose a compliant "offer_incentive" does it restart the offer
    cycle - same ranked_candidate_ids, same record_candidate_response
    accept/decline path, now with the incentive attached. A non-compliant
    or failed decision is persisted plainly, never silently upgraded.
    """
    record = db.query(RecoveryPlanRecord).filter_by(plan_id=plan_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="plan not found")

    if record.status != "exhausted":
        raise HTTPException(
            status_code=409,
            detail=(
                f"incentive fallback only triggers once the normal queue is "
                f"exhausted (status={record.status})"
            ),
        )

    ranked = record.ranked_candidate_ids or []
    statuses = dict(record.candidate_statuses or {})
    decline_history = [
        {"patient_id": pid, "response": statuses.get(pid, "declined")} for pid in ranked
    ]

    try:
        decision = decide_incentive(
            open_slot=record.open_slot,
            business_policy=business_policy,
            decline_history=decline_history,
        )
    except Exception as exc:
        record.message = f"Incentive decision failed: {exc}"
        db.commit()
        db.refresh(record)
        return plan_record_to_dict(record)

    slot_price = record.open_slot.get("price", 0)
    service = record.open_slot.get("service_type", "")
    compliant, violation = _incentive_within_policy(decision, business_policy, slot_price, service)
    if not compliant:
        decision = {
            "decision": "stop_recovery",
            "chosen_incentive": None,
            "reasoning": f"Model's choice was rejected by policy: {violation}",
            "rerank_required": False,
        }

    record.selected_incentive = decision
    record.stage = "INCENTIVE"
    record.message = decision.get("reasoning")

    if decision.get("decision") == "offer_incentive" and ranked:
        record.current_candidate_index = 0
        record.status = "pending"
        statuses[ranked[0]] = "offered"
        record.candidate_statuses = statuses
        record.current_offer_at = _utcnow()
    # continue_full_price / stop_recovery / no candidates left: status stays
    # "exhausted" - there is nothing left to offer.

    db.commit()
    db.refresh(record)
    return plan_record_to_dict(record)
