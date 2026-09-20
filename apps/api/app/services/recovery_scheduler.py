"""Autonomous orchestrator for the recovery queue.

Runs as a background asyncio loop, independent of any HTTP request or button
click. Each tick does exactly three jobs - it invents no ranking or decisions
of its own, it only decides WHEN to call functions prior milestones already
built and already use from real request paths:

1. A slot that just became free (cancelled_at is set) and has no plan yet for
   THIS cancellation gets run_recovery() - the same eligibility+ranking
   pipeline the dashboard button and the voice-agent background task use.
   run_recovery() is itself idempotent, so calling it every tick for a slot
   that already has a plan is a cheap no-op, not a re-rank.
2. A pending plan whose current offer has been outstanding longer than the
   active profile's recovery_rules.candidate_timeout_seconds with no response
   gets record_candidate_response(..., "timeout") - a real timeout window
   that actually elapses, never a fabricated decline/accept.
3. A plan that just exhausted its queue at full price gets
   apply_incentive_decision() exactly once, guarded by stage still being
   "NORMAL" (that call itself flips stage to "INCENTIVE", so it naturally
   never re-fires for the same exhaustion).

Real outbound calling (Twilio) is deliberately NOT triggered here - see
outreach_service.py's OutreachAttempt, which still waits on the owner's
POST /api/outreach/{id}/approve. Once that path is wired, this is where its
automatic trigger would be added.
"""

import asyncio
import datetime
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.business_policy import get_business_policy
from app.db.models.appointment import Appointment
from app.db.models.recovery import RecoveryPlanRecord
from app.db.session import SessionLocal
from app.services.business_profile_service import get_recovery_rules
from app.services.recovery_service import apply_incentive_decision, record_candidate_response
from app.services.slot_recovery import run_recovery

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = float(os.getenv("RECOVERY_POLL_INTERVAL_SECONDS", "3"))
# The offer timeout itself now comes from the active profile's
# recovery_rules.candidate_timeout_seconds (business_profile_service.py).


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """SQLite drops tzinfo on round-trip even for DateTime(timezone=True)
    columns; every value this app writes here is UTC, so a naive read-back
    is UTC too, not local time."""
    return value if value.tzinfo is not None else value.replace(tzinfo=datetime.timezone.utc)


def _plan_new_cancellations(db: Session) -> None:
    freed = db.execute(
        select(Appointment)
        .where(Appointment.status == "available")
        .where(Appointment.cancelled_at.isnot(None))
    ).scalars().all()
    for appt in freed:
        try:
            run_recovery(db, appt, cancelled_by=appt.last_cancelled_by)
        except Exception:
            logger.exception("autonomous run_recovery failed for slot %s", appt.id)


def _advance_timed_out_offers(db: Session, timeout_seconds: float) -> None:
    pending = db.execute(
        select(RecoveryPlanRecord)
        .where(RecoveryPlanRecord.status == "pending")
        .where(RecoveryPlanRecord.current_offer_at.isnot(None))
    ).scalars().all()
    now = _utcnow()
    for plan in pending:
        offered_at = _as_utc(plan.current_offer_at)
        if (now - offered_at).total_seconds() >= timeout_seconds:
            try:
                record_candidate_response(db, plan.plan_id, "timeout")
            except Exception:
                logger.exception("autonomous timeout advance failed for plan %s", plan.plan_id)


def _apply_incentive_where_exhausted(db: Session) -> None:
    exhausted = db.execute(
        select(RecoveryPlanRecord)
        .where(RecoveryPlanRecord.status == "exhausted")
        .where(RecoveryPlanRecord.stage == "NORMAL")
    ).scalars().all()
    for plan in exhausted:
        try:
            apply_incentive_decision(db, plan.plan_id, get_business_policy(db))
        except Exception:
            logger.exception("autonomous incentive decision failed for plan %s", plan.plan_id)


def tick() -> None:
    """One full pass of all three jobs. Own session; never raises."""
    db = SessionLocal()
    try:
        rules = get_recovery_rules(db)
        if not rules["auto_recovery_enabled"]:
            return
        _plan_new_cancellations(db)
        _advance_timed_out_offers(db, rules["candidate_timeout_seconds"])
        if rules["incentive_fallback_enabled"]:
            _apply_incentive_where_exhausted(db)
    except Exception:
        logger.exception("recovery scheduler tick failed")
    finally:
        db.close()


async def run_forever() -> None:
    """Runs each tick in a worker thread - a tick can make real Nemotron
    HTTP calls that take several seconds, and must not stall the event loop
    (and therefore every other request) while doing so."""
    logger.info(
        "recovery scheduler started (poll=%ss; offer timeout is per-business-profile)",
        POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            logger.exception("recovery scheduler tick raised past its own guard")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
