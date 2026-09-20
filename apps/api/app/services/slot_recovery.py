"""Recovery for a slot that has just become free: who should we offer it to?

Distinct from recovery_service.py, which persists the resulting plan and runs
the accept/decline/timeout state machine on top of it. This module is the step
before that - matching and ranking candidates for a freed slot and queueing the
best one for owner approval.

Extracted so the same path runs whether the slot was freed by the dashboard
(POST /api/recovery/from-cancellation) or by a patient cancelling on a live
phone call (POST /api/voice/cancel). Before this existed, only the dashboard
route could start recovery, which meant the product's central event - someone
cancelling - did not actually trigger the product.

Assumes the slot is ALREADY free; it does not release it.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.mock_store import RECOVERY_PLANS, new_plan_id
from app.agents.nemotron.ranker import rank_candidates
from app.db.models.appointment import Appointment
from app.db.session import SessionLocal
from app.services.appointment_service import cancel_appointment
from app.services.business_profile_service import get_recovery_rules
from app.services.outreach_service import evaluate_candidate, maybe_auto_call
from app.services.recovery_matcher import find_candidates
from app.services.recovery_service import (
    get_latest_plan_for_slot,
    plan_record_to_dict,
    save_recovery_plan,
)

logger = logging.getLogger(__name__)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """Appointment.cancelled_at is a plain DateTime column (no timezone=True),
    so Postgres round-trips it as naive even though every write into it is
    UTC (see appointment_service.cancel_appointment). RecoveryPlanRecord.
    created_at IS timezone-aware, so comparing the two directly raises
    "can't compare offset-naive and offset-aware datetimes" - this normalizes
    either side to a comparable, correctly-UTC value."""
    return value if value.tzinfo is not None else value.replace(tzinfo=datetime.timezone.utc)


def slot_payload(slot: Appointment) -> dict:
    return {
        "slot_id": slot.id,
        "provider": slot.provider,
        "service_type": slot.service,
        "start": slot.start_time.isoformat(),
        "duration_min": slot.duration_minutes,
        "price": slot.price,
    }


def run_recovery(db: Session, slot: Appointment, cancelled_by: str | None = None) -> dict:
    """Rank eligible patients for a freed slot, persist the plan, queue the best one.

    Ordering matters here. Everything deterministic (eligibility) happens and is
    persisted before any model call, so a Nemotron outage degrades to "we know
    who is eligible but could not rank them" rather than losing the whole event.

    Idempotent per cancellation: this now runs from three places (the dashboard
    route, the voice-agent background task, and the autonomous scheduler), so
    if a plan already covers this exact cancellation, return it rather than
    re-ranking and creating a duplicate.
    """
    existing = get_latest_plan_for_slot(db, slot.id)
    if existing is not None and (
        slot.cancelled_at is None or _as_utc(existing.created_at) >= _as_utc(slot.cancelled_at)
    ):
        return {**plan_record_to_dict(existing), "eligible": [], "excluded": [], "outreach": None}

    eligible, excluded = find_candidates(db, slot.start_time, slot.provider, exclude_slot_id=slot.id)
    open_slot = slot_payload(slot)

    if not eligible:
        plan_id = new_plan_id()
        plan = {
            "plan_id": plan_id,
            "open_slot": open_slot,
            "candidates": [],
            "ranked_candidate_ids": [],
            "current_candidate_index": 0,
            "stage": "NORMAL",
            "selected_incentive": None,
            "status": "no_candidates",
            "revenue_at_risk": slot.price,
            "message": "No stored intent matches this slot - it would go unfilled.",
        }
        # Persisted (not just returned) so the autonomous scheduler recognizes
        # this cancellation as already handled and doesn't retry it forever.
        save_recovery_plan(db, plan, slot_id=slot.id, cancelled_by=cancelled_by)
        return {**plan, "eligible": [], "excluded": excluded, "outreach": None}

    plan_id = new_plan_id()
    try:
        ranking = rank_candidates(open_slot, eligible)
    except Exception as exc:
        # Cancellation and eligibility already happened and are real; only
        # ranking failed. Persist that plainly rather than faking an order.
        logger.exception("ranking failed for slot %s", slot.id)
        plan = {
            "plan_id": plan_id,
            "open_slot": open_slot,
            "candidates": eligible,  # unranked - labelled by status below
            "ranked_candidate_ids": [],
            "current_candidate_index": 0,
            "stage": "NORMAL",
            "selected_incentive": None,
            "status": "ranking_failed",
            "revenue_at_risk": slot.price,
            "message": f"Eligibility found {len(eligible)} candidate(s), but ranking failed: {exc}",
        }
        RECOVERY_PLANS[plan_id] = plan
        save_recovery_plan(db, plan, slot_id=slot.id, cancelled_by=cancelled_by)
        return {**plan, "eligible": eligible, "excluded": excluded, "outreach": None}

    # Selection happens BEFORE the plan is persisted. save_recovery_plan is a
    # plain INSERT with no upsert, so the plan is written exactly once and its
    # status has to be correct the first time.
    #
    # All three lookups below read ids the MODEL chose, so none can be assumed
    # to resolve: it can rank nobody, or name a patient that is not in the
    # eligible set. Unguarded, that raised IndexError/StopIteration and left
    # the slot cancelled with no outreach and nothing recorded to say why.
    # Nemotron's own ranked output only carries patient_id/match_score/reason
    # (whatever shape it chose to return) - re-attach the currently_booked_*
    # fields from the deterministic eligible list so the frontend can tell a
    # rearrangement candidate (already booked elsewhere) from a plain fill.
    eligible_by_id = {c["patient_id"]: c for c in eligible}
    ranked_candidates = ranking.get("candidates") or eligible
    for candidate in ranked_candidates:
        source = eligible_by_id.get(candidate.get("patient_id"))
        if source:
            candidate["currently_booked_slot_id"] = source.get("currently_booked_slot_id")
            candidate["currently_booked_start"] = source.get("currently_booked_start")

    max_attempts = get_recovery_rules(db)["max_recovery_attempts"]
    ranked_ids = (ranking.get("ranked_candidate_ids") or [])[:max_attempts]
    top_candidate = None
    top_score = None
    if ranked_ids:
        top_id = ranked_ids[0]
        top_candidate = next((c for c in eligible if c["patient_id"] == top_id), None)
        top_score = next(
            (c["match_score"] for c in ranking.get("candidates", []) if c["patient_id"] == top_id),
            None,
        )
    selection_failed = top_candidate is None or top_score is None

    plan = {
        "plan_id": plan_id,
        "open_slot": open_slot,
        "candidates": ranked_candidates,
        "ranked_candidate_ids": ranked_ids,
        "current_candidate_index": 0,
        "stage": "NORMAL",
        "selected_incentive": None,
        "status": "selection_failed" if selection_failed else "pending",
        "revenue_at_risk": slot.price,
    }
    if selection_failed:
        plan["message"] = (
            f"Ranking returned {len(ranked_ids)} id(s) but none resolved to an "
            "eligible candidate, so no outreach was queued."
        )
    RECOVERY_PLANS[plan_id] = plan
    save_recovery_plan(db, plan, slot_id=slot.id, cancelled_by=cancelled_by)

    if selection_failed:
        logger.warning(
            "slot %s: ranking produced no usable candidate (ranked=%s)", slot.id, ranked_ids
        )
        return {**plan, "eligible": eligible, "excluded": excluded, "outreach": None}

    # Ranking says who COULD take the slot; this decides whether calling the
    # top match is worth doing and drafts what the agent should say.
    outreach = evaluate_candidate(db, open_slot, top_candidate, top_score, slot.price)
    outreach = maybe_auto_call(db, outreach)

    return {
        **plan,
        "eligible": eligible,
        "excluded": excluded,
        "outreach": {
            "id": outreach.id,
            "should_call": outreach.should_call,
            "reason": outreach.decision_reason,
            "incentive": outreach.incentive,
            "call_brief": outreach.call_brief,
            "status": outreach.status,
        },
    }


def cascade_after_move(db: Session, patient_id: str, filled_slot_id: int) -> dict | None:
    """Called right after a recovery offer is ACCEPTED. If the accepting
    patient was already booked into a different appointment, this was a
    rearrangement, not a plain fill: their old slot is now free, so recovery
    runs on it too. Returns that new recovery result, or None if this
    candidate had no other booking (the ordinary "filled a gap" case).

    This is what turns one cancellation into a chain: slot A opens, the best
    match for A turns out to be a patient already booked into (a worse-fit)
    slot B, moving them frees B, and B's own best match might itself already
    be booked elsewhere, and so on - it terminates naturally once a freed
    slot's best remaining candidates are all genuinely new fills (or none at
    all), which is exactly the "one awkward slot left over" outcome.
    """
    other = db.execute(
        select(Appointment).where(
            Appointment.customer_id == patient_id,
            Appointment.status == "booked",
            Appointment.id != filled_slot_id,
        )
    ).scalars().first()
    if other is None:
        return None

    freed = cancel_appointment(db, other.id)
    logger.info(
        "cascade: moving %s into slot %s freed their old slot %s",
        patient_id, filled_slot_id, other.id,
    )
    return run_recovery(db, freed, cancelled_by=patient_id)


def recover_freed_slot(slot_id: int) -> None:
    """Background-task entry point. Opens its own session; never raises.

    A failure here must not surface to the patient who just cancelled - their
    cancellation already succeeded and is committed.
    """
    db = SessionLocal()
    try:
        slot = db.get(Appointment, slot_id)
        if slot is None:
            logger.warning("freed slot %s vanished before recovery", slot_id)
            return
        result = run_recovery(db, slot, cancelled_by=slot.last_cancelled_by)
        out = result.get("outreach")
        if out:
            logger.info(
                "recovery for slot %s: outreach %s should_call=%s",
                slot_id, out["id"], out["should_call"],
            )
        else:
            logger.info("recovery for slot %s: no eligible candidates", slot_id)
    except Exception:
        logger.exception("recovery failed for freed slot %s", slot_id)
    finally:
        db.close()
