"""Persists the RecoveryPlan dicts Kevin's /api/recovery/* routes build, and
advances the accept/decline/timeout state machine on top of that persisted
state. No ranking/reasoning here - candidates arrive already ranked; this
only decides who the "current" offer belongs to and what happens next.
"""

import datetime
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.nemotron.incentive import decide_incentive
from app.db.models.recovery import RecoveryPlanRecord
from app.services.appointment_service import book_slot
from app.services.business_profile_service import get_business_policy, get_recovery_rules
from app.services.outreach_service import evaluate_candidate, maybe_auto_call, place_call_for_attempt

logger = logging.getLogger(__name__)


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


def offer_to_current_candidate(
    db: Session, record: RecoveryPlanRecord, incentive_override: dict | None = None
) -> None:
    """Make the offer to whoever the plan is currently on: build their
    outreach, place the call if auto-calling is on, and if they simply
    cannot be reached, move straight past them.

    That last part is the point. A candidate with no phone number, or whose
    call ElevenLabs refused, used to leave the plan sitting on them until
    the offer timed out minutes later - the queue looked alive while nobody
    was being called and nothing was going to happen. Being uncallable is
    known immediately, so it advances immediately, and the skip recurses
    until someone is reachable or the queue is genuinely spent.
    """
    ranked = record.ranked_candidate_ids or []
    idx = record.current_candidate_index
    if idx >= len(ranked):
        return
    patient_id = ranked[idx]
    candidate = next(
        (c for c in (record.candidates or []) if c.get("patient_id") == patient_id), None
    )
    if candidate is None:
        return

    try:
        attempt = evaluate_candidate(
            db,
            record.open_slot,
            candidate,
            candidate.get("match_score", 0.0),
            record.revenue_at_risk or 0.0,
            incentive_override=incentive_override,
        )
        attempt = maybe_auto_call(db, attempt, candidate=candidate)
    except Exception:
        logger.exception("could not make an offer to %s on plan %s", patient_id, record.plan_id)
        return

    if attempt.should_call and attempt.status != "failed":
        return  # dialed, or waiting in the manual approval queue

    logger.info(
        "skipping %s on plan %s: %s",
        patient_id, record.plan_id, attempt.call_error or "not worth calling",
    )
    record_candidate_response(db, record.plan_id, "skipped")


def _cheapest_compliant_incentive(business_policy: dict, record: RecoveryPlanRecord) -> dict | None:
    """The least generous incentive in the approved list that still passes the
    policy gate, or None if nothing in the list does.

    Least generous on purpose: this runs when the model declined to choose,
    so it should concede as little as the owner's own policy allows.
    """
    price = record.open_slot.get("price", 0)
    service = record.open_slot.get("service_type", "")

    def concession(incentive: dict) -> float:
        if incentive.get("type") == "percent_discount":
            return price * incentive.get("value", 0) / 100
        return float(incentive.get("value", 0))

    for incentive in sorted(business_policy.get("allowed_incentives", []), key=concession):
        candidate = {
            "decision": "offer_incentive",
            "chosen_incentive": incentive["id"],
            "reasoning": (
                f"Offered automatically: business policy authorizes an incentive from this "
                f"point in the queue onward."
            ),
            "rerank_required": False,
        }
        compliant, _ = _incentive_within_policy(candidate, business_policy, price, service)
        if compliant:
            return candidate
    return None


def _authorized_incentive(db: Session, record: RecoveryPlanRecord, attempt_number: int) -> dict | None:
    """The incentive this offer is allowed to carry, or None for full price.

    Nothing here decides an incentive on its own - it asks Nemotron
    (decide_incentive) and then runs the same deterministic policy gate the
    exhaustion fallback uses, so an early discount can't exceed the caps an
    owner set. Returns None whenever incentives are switched off, this
    attempt is too early to sweeten, the model chose not to, or its choice
    failed the gate.
    """
    rules = get_recovery_rules(db)
    if not rules["incentive_fallback_enabled"]:
        return None
    if attempt_number < rules["incentive_from_attempt"]:
        return None

    business_policy = get_business_policy(db)
    statuses = dict(record.candidate_statuses or {})
    ranked = record.ranked_candidate_ids or []
    # What was already offered and still refused goes in, not just who said
    # no: an incentive that has now been turned down is evidence the next
    # offer needs to be worth more than it, which is what lets the third call
    # escalate past the second instead of repeating it. The policy gate below
    # still caps whatever comes back.
    previously_offered = (record.selected_incentive or {}).get("chosen_incentive")
    decline_history = [
        {
            "patient_id": pid,
            "response": statuses.get(pid, "declined"),
            "incentive_offered": previously_offered,
        }
        for pid in ranked
        if statuses.get(pid) in ("declined", "expired")
    ]
    hours_until = (
        datetime.datetime.fromisoformat(record.open_slot["start"]) - datetime.datetime.now()
    ).total_seconds() / 3600

    try:
        decision = decide_incentive(
            open_slot={**record.open_slot, "hours_until_appointment": round(hours_until, 1)},
            business_policy=business_policy,
            decline_history=decline_history,
        )
    except Exception:
        logger.exception("incentive decision failed for plan %s", record.plan_id)
        decision = {}

    compliant, violation = _incentive_within_policy(
        decision,
        business_policy,
        record.open_slot.get("price", 0),
        record.open_slot.get("service_type", ""),
    )
    if not compliant:
        logger.info("incentive rejected by policy for plan %s: %s", record.plan_id, violation)
        decision = {}

    if decision.get("decision") != "offer_incentive":
        # incentive_from_attempt is an instruction from the business, not a
        # suggestion: past this point in the queue the offer is authorized to
        # carry a discount. The model still chooses WHICH one whenever it
        # cooperates - this only covers it declining outright, erroring, or
        # naming something the policy gate rejects, where the alternative was
        # silently calling at full price after the owner asked not to.
        # Whatever is picked here went through allowed_incentives and the same
        # cap/floor check, so it can never exceed what they approved.
        decision = _cheapest_compliant_incentive(business_policy, record)
        if decision is None:
            logger.info("no policy-compliant incentive available for plan %s", record.plan_id)
            return None

    record.selected_incentive = decision
    record.stage = "INCENTIVE"
    record.message = decision.get("reasoning")
    db.commit()
    db.refresh(record)
    return decision


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
    - "skipped": the same advance, for a candidate who was never reachable
      at all (no phone number, telephony refused the call, or Nemotron
      judged the call not worth placing). Distinct from "declined" because
      nobody actually told us no - and it happens immediately rather than
      after an offer window nobody was ever going to answer.
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

    elif response in ("declined", "timeout", "skipped"):
        statuses[current_patient_id] = {
            "declined": "declined", "timeout": "expired", "skipped": "skipped",
        }[response]
        if idx + 1 >= len(ranked):
            # Stay on the last candidate rather than pointing one past the
            # end. "exhausted" already says the queue is spent, and an index
            # outside the list is just a foot-gun for anything that reads
            # ranked[current_candidate_index] to show who we are on.
            record.status = "exhausted"
            record.current_offer_at = None
            record.candidate_statuses = statuses
        else:
            record.current_candidate_index = idx + 1
            next_patient_id = ranked[record.current_candidate_index]
            # Unconditional, not setdefault: a candidate re-offered during the
            # incentive round may already have "declined"/"expired" from the
            # earlier full-price round. Being offered again must overwrite
            # that stale status, not be suppressed by it.
            statuses[next_patient_id] = "offered"
            record.current_offer_at = _utcnow()
            record.candidate_statuses = statuses
            db.commit()
            db.refresh(record)

            # Attempt number is 1-based: the person we just moved to is
            # attempt current_candidate_index + 1. From incentive_from_attempt
            # onward the offer may carry a discount, so "first person said no"
            # leads to a sweetened second call, not the same pitch again.
            # A skip does not earn anyone a discount - nobody refused
            # anything, so the offer stays at the price it was.
            incentive_override = None
            if response != "skipped":
                try:
                    incentive_override = _authorized_incentive(
                        db, record, attempt_number=record.current_candidate_index + 1
                    )
                except Exception:
                    logger.exception("incentive check failed for plan %s", record.plan_id)
            offer_to_current_candidate(db, record, incentive_override=incentive_override)
            db.refresh(record)
            return plan_record_to_dict(record)

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
        db.commit()
        db.refresh(record)

        # The re-offer needs its OWN outreach attempt and call brief - the
        # original one (from the full-price round) was generated before this
        # discount existed, so its call_brief never mentions it. Passing the
        # already-decided, already-policy-checked decision straight through
        # (incentive_override) means this doesn't ask Nemotron to pick an
        # incentive a second time, just to draft the call around it.
        reoffer_candidate = next(
            (c for c in (record.candidates or []) if c.get("patient_id") == ranked[0]), None
        )
        if reoffer_candidate is not None:
            try:
                outreach = evaluate_candidate(
                    db,
                    record.open_slot,
                    reoffer_candidate,
                    reoffer_candidate.get("match_score", 0.0),
                    record.revenue_at_risk or 0.0,
                    incentive_override=decision,
                    business_policy=business_policy,
                )
                maybe_auto_call(db, outreach, candidate=reoffer_candidate)
            except Exception:
                logger.exception(
                    "outreach/auto-call failed for incentive re-offer to %s on plan %s",
                    ranked[0], record.plan_id,
                )
        return plan_record_to_dict(record)

    # continue_full_price / stop_recovery / no candidates left: status stays
    # "exhausted" - there is nothing left to offer.
    db.commit()
    db.refresh(record)
    return plan_record_to_dict(record)


def offer_incentive_to_current_candidate(db: Session, plan_id: str, business_policy: dict) -> dict:
    """Owner override: attach a discount to whoever is the CURRENT offer
    right now, without waiting for the rest of the ranked list to be tried
    first. apply_incentive_decision above only fires once the whole queue is
    exhausted - this is for when an owner (or the pace of a live demo)
    decides that's taking too long and wants to sweeten the current offer
    immediately instead.

    Same Nemotron call and the same deterministic policy gate
    (_incentive_within_policy) as the automatic path - an owner clicking
    this can't grant a bigger discount than the policy allows any more than
    the automatic fallback can.
    """
    record = db.query(RecoveryPlanRecord).filter_by(plan_id=plan_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="plan not found")
    if record.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"plan {plan_id} has no current offer to incentivize (status={record.status})",
        )

    ranked = record.ranked_candidate_ids or []
    idx = record.current_candidate_index
    if idx >= len(ranked):
        raise HTTPException(status_code=409, detail=f"plan {plan_id} has no current candidate")
    current_patient_id = ranked[idx]

    hours_until = (
        datetime.datetime.fromisoformat(record.open_slot["start"]) - datetime.datetime.now()
    ).total_seconds() / 3600
    statuses = dict(record.candidate_statuses or {})
    decline_history = [
        {"patient_id": pid, "response": statuses.get(pid, "declined")} for pid in ranked[:idx]
    ]

    decision = decide_incentive(
        open_slot={**record.open_slot, "hours_until_appointment": round(hours_until, 1)},
        business_policy=business_policy,
        decline_history=decline_history,
    )

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
    db.commit()
    db.refresh(record)

    if decision.get("decision") == "offer_incentive":
        current_candidate = next(
            (c for c in (record.candidates or []) if c.get("patient_id") == current_patient_id), None
        )
        if current_candidate is not None:
            outreach = evaluate_candidate(
                db,
                record.open_slot,
                current_candidate,
                current_candidate.get("match_score", 0.0),
                record.revenue_at_risk or 0.0,
                incentive_override=decision,
                business_policy=business_policy,
            )
            # An explicit owner click, not the automatic-on-decline path -
            # this places the call immediately regardless of
            # recovery_rules.auto_call_enabled, the same as clicking
            # Approve on any other outreach attempt.
            if outreach.should_call:
                outreach.status = "approved"
                place_call_for_attempt(db, outreach)

    return plan_record_to_dict(record)
