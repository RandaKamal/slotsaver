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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.business_policy import BUSINESS_POLICY
from app.agents.nemotron.incentive import decide_incentive
from app.agents.nemotron.outreach import decide_outreach, generate_call_brief
from app.db.models.outreach import OutreachAttempt
from app.db.models.preference import PreferenceRecord

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


def evaluate_top_candidate(
    db: Session,
    open_slot: dict,
    top_candidate: dict,
    match_score: float,
    revenue_at_risk: float,
) -> OutreachAttempt:
    """Runs the full decision pipeline for one candidate and persists the result."""
    patient_id = top_candidate["patient_id"]
    hours_until = (
        datetime.datetime.fromisoformat(open_slot["start"]) - datetime.datetime.now()
    ).total_seconds() / 3600

    incentive = None
    if match_score < 0.9:  # a near-perfect match doesn't need to be bought
        incentive_decision = decide_incentive(
            open_slot={**open_slot, "hours_until_appointment": round(hours_until, 1)},
            business_policy=BUSINESS_POLICY,
            decline_history=[],
        )
        if incentive_decision.get("decision") == "offer_incentive":
            incentive = incentive_decision

    contact_history = _contact_history(db, patient_id)
    outreach_decision = decide_outreach(
        open_slot=open_slot,
        candidate=top_candidate,
        match_score=match_score,
        incentive=incentive,
        contact_history=contact_history,
        business_policy=BUSINESS_POLICY,
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
            "said": top_candidate.get("said"),
            "soft_preferences": top_candidate.get("soft_preferences"),
            "requested_time": top_candidate.get("requested_time"),
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
        phone_number = record.phone_number if record else top_candidate.get("phone_number")
    else:
        phone_number = top_candidate.get("phone_number")

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
