"""Turns a ranked candidate into a call the owner can approve - or a documented
decision not to call at all.

Pipeline for the top-ranked candidate on a freed slot:
  1. decide_incentive()   - already existed; picks from the approved list only.
  2. decide_outreach()    - NEW: is this call worth placing at all?
  3. generate_call_brief() - NEW: if yes, what should the agent actually say?
  4. persist an OutreachAttempt in 'pending_approval' - nothing dials until an
     owner approves it via POST /api/outreach/{id}/approve.

Every candidate that reaches step 1 gets a row, including should_call=False
ones - a documented "we decided not to call" is exactly as important as a
decision to call, for both the demo and for not pestering patients.
"""

import datetime
import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.business_policy import get_business_policy
from app.agents.nemotron.incentive import decide_incentive
from app.agents.nemotron.outreach import decide_outreach, generate_call_brief
from app.db.models.appointment import Appointment
from app.db.models.outreach import OutreachAttempt
from app.db.models.preference import PreferenceRecord
from app.services.business_profile_service import get_recovery_rules
from app.services.call_service import CallNotConfigured, place_call
from app.services.patient_memory import build_patient_brief

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 7


def _contact_history(db: Session, patient_id: str) -> dict:
    """Recent outreach attempts for this patient - the fatigue signal decide_outreach checks.

    'recent_declines' is not yet populated: it should count times the PATIENT
    declined during a call, but no call has ever actually completed (Twilio
    isn't wired yet). It stays 0 until a real call-outcome webhook exists;
    marked here so nobody mistakes silence for "no history".
    """
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_LOOKBACK_DAYS)
    recent = db.execute(
        select(func.count())
        .select_from(OutreachAttempt)
        .where(OutreachAttempt.patient_id == patient_id)
        .where(OutreachAttempt.status.in_(("approved", "placed", "failed")))
        .where(OutreachAttempt.created_at >= since)
    ).scalar_one()
    return {
        "recent_contact_attempts_7d": recent,
        "recent_declines": 0,  # TODO: populate once call outcomes are tracked
    }


def evaluate_candidate(
    db: Session,
    open_slot: dict,
    candidate: dict,
    match_score: float,
    revenue_at_risk: float,
    incentive_override: dict | None = None,
    business_policy: dict | None = None,
    allow_self_decided_incentive: bool = True,
) -> OutreachAttempt:
    """Runs the full decision pipeline for one candidate and persists the result.

    Works the same for the first candidate offered a slot at full price and
    for a later candidate in the ranked queue - "top" was never actually
    special here, it was just the only one ever evaluated. incentive_override
    is set by the incentive-fallback round (apply_incentive_decision already
    ran decide_incentive with the real decline history) so this doesn't
    re-decide an incentive independently and produce a call brief that
    doesn't mention the discount that was actually approved.
    """
    patient_id = candidate["patient_id"]
    hours_until = (
        datetime.datetime.fromisoformat(open_slot["start"]) - datetime.datetime.now()
    ).total_seconds() / 3600

    # A caller that already resolved the active profile's policy (e.g.
    # apply_incentive_decision, which takes it as its own parameter) passes
    # it straight through instead of this re-querying the DB and risking a
    # different view of it within the same request.
    if business_policy is None:
        business_policy = get_business_policy(db)

    if incentive_override is not None:
        incentive = incentive_override
    else:
        incentive = None
        # The full-price round must actually be full price. Deciding an
        # incentive here as well meant the very first candidate was offered a
        # discount before anyone had declined anything - the plain ask, which
        # is the cheapest way to fill the slot, never happened, and
        # recovery_rules.incentive_from_attempt was quietly bypassed.
        if allow_self_decided_incentive and match_score < business_policy["incentive_score_threshold"]:  # a near-perfect match doesn't need to be bought
            incentive_decision = decide_incentive(
                open_slot={**open_slot, "hours_until_appointment": round(hours_until, 1)},
                business_policy=business_policy,
                decline_history=[],
            )
            if incentive_decision.get("decision") == "offer_incentive":
                incentive = incentive_decision

    contact_history = _contact_history(db, patient_id)
    outreach_decision = decide_outreach(
        open_slot=open_slot,
        candidate=candidate,
        match_score=match_score,
        incentive=incentive,
        contact_history=contact_history,
        business_policy=business_policy,
    )
    should_call = bool(outreach_decision.get("should_call"))
    reason = outreach_decision.get("reason", "")

    call_brief: dict = {}
    if should_call:
        record = db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.patient_id == patient_id)
            .order_by(PreferenceRecord.created_at.desc())
        ).scalars().first()
        patient_intent = {
            "said": candidate.get("said"),
            "soft_preferences": candidate.get("soft_preferences"),
            "requested_time": candidate.get("requested_time"),
        }
        try:
            call_brief = generate_call_brief(open_slot, patient_intent, incentive)
        except Exception:
            logger.exception("call brief generation failed for patient %s", patient_id)
            call_brief = {
                "tone": "warm",
                "opening_line": f"Hi, this is SlotSaver calling about an opening with {open_slot['provider']}.",
                "key_points": [],
                "incentive_pitch": None,
            }
        phone_number = record.phone_number if record else candidate.get("phone_number")
    else:
        phone_number = candidate.get("phone_number")

    attempt = OutreachAttempt(
        slot_id=open_slot["slot_id"],
        patient_id=patient_id,
        phone_number=phone_number,
        match_score=match_score,
        revenue_at_risk=revenue_at_risk,
        should_call=should_call,
        decision_reason=reason,
        incentive=incentive,
        call_brief=call_brief,
        status="pending_approval",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def place_call_for_attempt(db: Session, attempt: OutreachAttempt) -> OutreachAttempt:
    """Actually dials, whether triggered by an owner's click (POST
    /api/outreach/{id}/approve) or automatically (see maybe_auto_call below).
    One shared place for "how a call actually gets placed" so both paths
    can't drift - see call_service.place_call for the ElevenLabs/Twilio
    request itself.
    """
    slot_row = db.get(Appointment, attempt.slot_id)
    slot = (
        {
            "provider": slot_row.provider,
            "service_type": slot_row.service,
            "start": slot_row.start_time.strftime("%A %d %B at %I:%M %p"),
        }
        if slot_row
        else None
    )
    try:
        response = place_call(attempt, slot, build_patient_brief(db, attempt.patient_id))
        # Kept so the call's outcome can be read back when it ends, instead of
        # the queue having to advance on a blind timeout - see call_outcome.py.
        conversation_id = (response or {}).get("conversation_id")
        if conversation_id:
            attempt.status = "placed"
            attempt.conversation_id = conversation_id
        else:
            # ElevenLabs answers 200 with a null conversation id when the call
            # never actually started (no credits, for one). Calling that
            # "placed" strands the attempt: the outcome job only reads rows
            # that have a conversation id, so nothing would ever resolve it.
            attempt.status = "failed"
            attempt.call_error = (
                "ElevenLabs accepted the request but returned no conversation id - "
                "the call never started"
            )
            logger.error("attempt %s: no conversation id returned; call did not start", attempt.id)
    except CallNotConfigured as exc:
        logger.info("attempt %s is not callable: %s", attempt.id, exc)
        attempt.status = "failed"
        attempt.call_error = str(exc)
    except Exception as exc:
        logger.exception("call placement failed for attempt %s", attempt.id)
        attempt.status = "failed"
        attempt.call_error = f"{type(exc).__name__}: {exc}"
    db.commit()
    db.refresh(attempt)
    return attempt


def maybe_auto_call(db: Session, attempt: OutreachAttempt, candidate: dict | None = None) -> OutreachAttempt:
    """Places the call immediately, with no owner approval, if the active
    business profile has opted into it (recovery_rules.auto_call_enabled -
    the thing "the business owner has to agree on beforehand"). Otherwise
    leaves the attempt in 'pending_approval' for the existing manual queue,
    unchanged from today's behavior.

    EVERY ranked candidate is called, including one already booked
    elsewhere: offering them a slot that fits their stored preference better
    is a real call to make ("a Tuesday morning opened up - want to move?"),
    and skipping them stalled the whole queue on a candidate nobody would
    ever dial. Calls stay sequential because the next offer is only placed
    once the previous call has ended (recovery_scheduler
    ._resolve_finished_calls), so this cannot put two calls on one line.
    """
    if not attempt.should_call:
        return attempt
    try:
        auto_call_enabled = get_recovery_rules(db)["auto_call_enabled"]
    except HTTPException:
        # No active business profile configured yet - default to the safe,
        # non-disruptive behavior (leave it for manual approval) rather than
        # taking down the whole recovery flow over a missing setup step.
        return attempt
    if not auto_call_enabled:
        return attempt
    attempt.status = "approved"
    return place_call_for_attempt(db, attempt)
