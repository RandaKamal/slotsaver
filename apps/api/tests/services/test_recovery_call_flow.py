"""End-to-end cover for the outbound recovery-call state machine.

The path under test is the whole loop, not one function:

    cancellation -> recovery plan -> OutreachAttempt for candidate 1
    -> call placed -> conversation ends without a booking
    -> candidate 1 declined -> plan advances -> OutreachAttempt for
    candidate 2 -> candidate 2 called -> incentive applied per
    recovery_rules.incentive_from_attempt

Only the two genuinely external things are faked: Nemotron (ranking,
outreach and incentive decisions) and ElevenLabs (the outbound-call POST
and the conversation-status GET). Everything between them - eligibility,
the business profile, the plan state machine, the scheduler's outcome
resolution - runs for real against an in-memory SQLite database, because
that is where every bug this file exists for actually lived.
"""

import datetime
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.appointment import Appointment
from app.db.models.outreach import OutreachAttempt
from app.db.models.preference import PreferenceRecord
from app.db.models.recovery import RecoveryPlanRecord
from app.db.seed_business_profiles import seed_business_profiles
from app.db.session import Base
from app.services import recovery_scheduler
from app.services.recovery_service import get_latest_plan_for_slot
from app.services.slot_recovery import run_recovery

# Telephony config the call path requires before it will even build a
# request. Set for every test so a CallNotConfigured only ever means the
# thing a given test is actually about (usually: no phone number).
CALL_ENV = {
    "ELEVENLABS_API_KEY": "test-key",
    "ELEVENLABS_PHONE_AGENT_ID": "test-phone-agent",
    "ELEVENLABS_PHONE_NUMBER_ID": "test-phone-number",
}

# Reserved-for-fiction numbers (555-01xx). A real dial attempt with these
# fails at the carrier instead of reaching a stranger, which is what makes
# them safe to seed.
MARIA_PHONE = "+15550100"
NOAH_PHONE = "+15550101"

FAKE_CALL_BRIEF = {
    "tone": "warm",
    "opening_line": "Hi, a slot just opened up with Dr. Lee.",
    "key_points": ["Tuesday morning, which is what you asked for."],
    "incentive_pitch": None,
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class RecoveryCallFlowTest(unittest.TestCase):
    """One freed slot, two ranked candidates, driven all the way through."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

        # The real seeded profiles, not a hand-written policy dict: whether
        # the active profile actually opts into auto-calling is one of the
        # things under test.
        seed_business_profiles(self.db)

        # Far enough out that no incentive time threshold or booking-notice
        # rule interferes, and parseable by the fromisoformat() calls in the
        # incentive path.
        self.slot_start = datetime.datetime.now() + datetime.timedelta(days=7)
        self.slot_start = self.slot_start.replace(microsecond=0)

        self.freed = Appointment(
            customer_id=None,
            service="Dental checkup",
            provider="Dr. Lee",
            start_time=self.slot_start,
            duration_minutes=30,
            price=120.0,
            status="available",
            cancelled_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            last_cancelled_by="patient-zoe",
        )
        self.db.add(self.freed)
        self.db.commit()
        self.db.refresh(self.freed)

        self._seed_candidate("patient-maria", MARIA_PHONE)
        self._seed_candidate("patient-noah", NOAH_PHONE)

    def tearDown(self):
        self.db.close()

    def _seed_candidate(self, patient_id: str, phone_number: str | None) -> None:
        self.db.add(
            PreferenceRecord(
                patient_id=patient_id,
                raw_text="Tell me if a Tuesday morning opens up with Dr. Lee.",
                status="extracted",
                notify_if_opens=True,
                hard_constraints={"excluded_providers": []},
                soft_preferences={
                    "preferred_time_ranges": ["morning"],
                    "preferred_provider": "Dr. Lee",
                    "provider_flexible": False,
                },
                requested_time="morning",
                expiry=(datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
                phone_number=phone_number,
                raw_extraction={},
            )
        )
        self.db.commit()

    # --- fakes -----------------------------------------------------------

    def _ranking(self):
        return {
            "ranked_candidate_ids": ["patient-maria", "patient-noah"],
            "candidates": [
                {"patient_id": "patient-maria", "match_score": 0.82, "reason": "asked for exactly this"},
                {"patient_id": "patient-noah", "match_score": 0.71, "reason": "mornings work"},
            ],
        }

    def _patches(self, call_response=None, call_side_effect=None, should_call=True,
                 incentive=None):
        """The four seams between this state machine and the outside world."""
        if call_response is None:
            call_response = FakeResponse(
                {"success": True, "message": "queued", "conversation_id": "conv-1", "callSid": "CA1"}
            )
        post_kwargs = (
            {"side_effect": call_side_effect}
            if call_side_effect is not None
            else {"return_value": call_response}
        )
        return [
            patch.dict(os.environ, CALL_ENV, clear=False),
            patch("app.services.slot_recovery.rank_candidates", return_value=self._ranking()),
            patch(
                "app.services.outreach_service.decide_outreach",
                return_value={"should_call": should_call, "reason": "worth calling"},
            ),
            patch("app.services.outreach_service.generate_call_brief", return_value=FAKE_CALL_BRIEF),
            # Both incentive seams, so a test that says nothing about
            # incentives still cannot reach the real Nemotron endpoint.
            patch(
                "app.services.outreach_service.decide_incentive",
                return_value={"decision": "continue_full_price", "chosen_incentive": None},
            ),
            patch(
                "app.services.recovery_service.decide_incentive",
                return_value=incentive or {"decision": "continue_full_price", "chosen_incentive": None},
            ),
            patch("app.services.call_service.httpx.post", **post_kwargs),
        ]

    def _run(self, patches, fn, *args, **kwargs):
        stack = []
        try:
            for p in patches:
                stack.append(p.__enter__())
            # DEMO_CALL_OVERRIDE_NUMBER would mask every phone-number bug
            # this file tests by redirecting all calls to one fixed number.
            os.environ.pop("DEMO_CALL_OVERRIDE_NUMBER", None)
            return fn(*args, **kwargs)
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

    def _attempts(self, patient_id: str | None = None) -> list[OutreachAttempt]:
        q = self.db.query(OutreachAttempt).order_by(OutreachAttempt.id)
        if patient_id:
            q = q.filter_by(patient_id=patient_id)
        return list(q)

    def _plan(self) -> RecoveryPlanRecord:
        plan = get_latest_plan_for_slot(self.db, self.freed.id)
        self.assertIsNotNone(plan, "no recovery plan was created for the freed slot")
        self.db.refresh(plan)
        return plan

    def _start_recovery(self, **kw):
        return self._run(self._patches(**kw), run_recovery, self.db, self.freed, "patient-zoe")

    def _finish_call(self, incentive=None):
        """Runs the scheduler job that reads a placed call's outcome, with
        ElevenLabs reporting the conversation as over and no booking made."""
        patches = self._patches(incentive=incentive) + [
            patch(
                "app.services.call_outcome.httpx.get",
                return_value=FakeResponse({"status": "done"}),
            )
        ]
        return self._run(patches, recovery_scheduler._resolve_finished_calls, self.db)

    # --- 1. automatic first call ----------------------------------------

    def test_first_candidate_is_called_automatically(self):
        self._start_recovery()

        attempts = self._attempts()
        self.assertEqual(len(attempts), 1, "expected exactly one outreach attempt for candidate 1")
        attempt = attempts[0]
        self.assertEqual(attempt.patient_id, "patient-maria")
        self.assertEqual(
            attempt.status,
            "placed",
            f"the seeded active profile must auto-call; attempt is {attempt.status!r}",
        )
        self.assertEqual(attempt.phone_number, MARIA_PHONE)
        self.assertEqual(attempt.conversation_id, "conv-1")

    # --- 2/3/4. call ends without booking -> decline -> next candidate ---

    def test_finished_call_without_booking_declines_and_calls_next(self):
        self._start_recovery()
        self._finish_call()

        first = self._attempts("patient-maria")[0]
        self.assertEqual(first.status, "completed_declined")

        plan = self._plan()
        self.assertEqual(plan.candidate_statuses["patient-maria"], "declined")
        self.assertEqual(plan.current_candidate_index, 1)
        self.assertEqual(plan.candidate_statuses["patient-noah"], "offered")
        self.assertEqual(plan.status, "pending")

        second = self._attempts("patient-noah")
        self.assertEqual(len(second), 1, "candidate 2 should get exactly one new outreach attempt")
        self.assertEqual(
            second[0].status, "placed", "candidate 2 should be dialed automatically, not queued"
        )
        self.assertEqual(second[0].phone_number, NOAH_PHONE)

    # --- 5. candidate 2 carries the configured incentive -----------------

    def test_second_candidate_receives_policy_allowed_incentive(self):
        """recovery_rules.incentive_from_attempt is 2 for the active profile,
        so the second offer - and only the second - may carry a discount."""
        self._start_recovery()
        first = self._attempts("patient-maria")[0]
        self.assertIsNone(first.incentive, "attempt 1 is before incentive_from_attempt")

        self._finish_call(
            incentive={
                "decision": "offer_incentive",
                "chosen_incentive": "10_percent_discount",
                "reasoning": "second call, policy allows it",
                "rerank_required": False,
            }
        )

        second = self._attempts("patient-noah")[0]
        self.assertIsNotNone(second.incentive, "attempt 2 should carry an incentive")
        self.assertEqual(second.incentive["chosen_incentive"], "10_percent_discount")

        plan = self._plan()
        self.assertEqual(plan.stage, "INCENTIVE")
        self.assertEqual(plan.selected_incentive["chosen_incentive"], "10_percent_discount")

    def test_incentive_refused_by_model_still_offers_a_compliant_one(self):
        self._start_recovery()
        self._finish_call(incentive={"decision": "continue_full_price", "chosen_incentive": None})

        second = self._attempts("patient-noah")[0]
        self.assertIsNotNone(
            second.incentive,
            "policy authorizes an incentive from attempt 2; the model declining to "
            "pick one must not silently drop it",
        )

    # --- 6. visible failures, never a frozen plan ------------------------

    def test_missing_phone_number_fails_visibly_and_advances(self):
        self.db.query(PreferenceRecord).filter_by(patient_id="patient-maria").update(
            {"phone_number": None}
        )
        self.db.commit()

        self._start_recovery()

        first = self._attempts("patient-maria")[0]
        self.assertEqual(
            first.status, "failed", "an uncallable attempt must not sit in a success-ish state"
        )
        self.assertTrue(first.call_error, "the reason the call could not be placed must be recorded")
        self.assertIn("phone number", first.call_error.lower())

        plan = self._plan()
        self.assertEqual(
            plan.current_candidate_index,
            1,
            "a candidate we cannot call must be skipped immediately, not waited out",
        )
        self.assertEqual(plan.candidate_statuses["patient-maria"], "skipped")
        self.assertEqual(self._attempts("patient-noah")[0].status, "placed")

    def test_null_conversation_id_fails_visibly_and_advances(self):
        """ElevenLabs answers 200 with conversation_id: null when the call
        never actually started. Recording that as 'placed' strands the
        attempt: the scheduler only reads outcomes for rows that have a
        conversation id, so nothing would ever resolve it."""
        # Only the FIRST call comes back without a conversation id. A blanket
        # failure would fail candidate 2 as well, and this test is about the
        # queue surviving one bad call, not about an outage.
        self._run(
            self._patches(
                call_side_effect=[
                    FakeResponse(
                        {"success": False, "message": "no credits",
                         "conversation_id": None, "callSid": None}
                    ),
                    FakeResponse(
                        {"success": True, "message": "queued",
                         "conversation_id": "conv-2", "callSid": "CA2"}
                    ),
                ]
            ),
            run_recovery,
            self.db,
            self.freed,
            "patient-zoe",
        )

        first = self._attempts("patient-maria")[0]
        self.assertNotEqual(
            first.status, "placed", "a call with no conversation id was never really placed"
        )
        self.assertEqual(first.status, "failed")
        self.assertTrue(first.call_error)

        plan = self._plan()
        self.assertEqual(plan.current_candidate_index, 1)
        self.assertEqual(self._attempts("patient-noah")[0].status, "placed")

    def test_elevenlabs_error_fails_visibly_and_advances(self):
        import httpx

        self._run(
            self._patches(call_side_effect=httpx.ConnectError("boom")),
            run_recovery,
            self.db,
            self.freed,
            "patient-zoe",
        )

        first = self._attempts("patient-maria")[0]
        self.assertEqual(first.status, "failed")
        self.assertTrue(first.call_error)

        plan = self._plan()
        self.assertEqual(
            plan.current_candidate_index, 1, "an ElevenLabs outage must not freeze the queue"
        )

    def test_should_call_false_skips_without_waiting_for_the_timeout(self):
        self._start_recovery(should_call=False)

        plan = self._plan()
        self.assertEqual(plan.candidate_statuses["patient-maria"], "skipped")
        self.assertEqual(plan.current_candidate_index, 1)
        self.assertEqual(plan.candidate_statuses["patient-noah"], "skipped")
        self.assertEqual(
            plan.status,
            "exhausted",
            "with nobody callable the plan must reach a terminal state, not stay pending",
        )
        self.assertIsNone(plan.current_offer_at)

    def test_a_candidate_is_never_dialed_twice_for_one_slot(self):
        """Regression: candidate 2 was called twice when the outcome job and
        the offer advance both reached maybe_auto_call for the same offer."""
        self._start_recovery()
        self._finish_call()
        # A second pass with the same state must find nothing left to do.
        self._finish_call()

        self.assertEqual(
            len(self._attempts("patient-noah")),
            1,
            "candidate 2 got more than one outreach attempt for the same slot",
        )


if __name__ == "__main__":
    unittest.main()
