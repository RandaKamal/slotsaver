"""Focused regression test for the incentive re-offer status bug.

Bug: when the incentive fallback re-offers a candidate who already has a
status from the earlier full-price round ("declined" or "expired"),
record_candidate_response used statuses.setdefault(...), which left the
stale status in place instead of reflecting that they're being called
again. Fixed by making that assignment unconditional (see
recovery_service.record_candidate_response).

Uses a throwaway in-memory SQLite DB and a patched decide_incentive so the
test is deterministic and makes no network calls - only the state machine
in recovery_service.py is under test here, not Nemotron or the ranker.
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.appointment import Appointment
from app.db.models.recovery import RecoveryPlanRecord
from app.db.session import Base
from app.services.recovery_service import apply_incentive_decision, record_candidate_response

# Same shape business_profile_service.get_business_policy resolves from the
# active profile's incentive_policy column - this test exercises the state
# machine directly, so it supplies the policy dict rather than a DB session.
BUSINESS_POLICY = {
    "max_discount_percent": 20,
    "minimum_revenue": 60,
    "allowed_incentives": [
        {"id": "10_percent_discount", "type": "percent_discount", "value": 10},
        {"id": "future_credit_10", "type": "fixed_credit", "value": 10},
        {"id": "referral_offer_15", "type": "referral_offer", "value": 15},
    ],
    "incentive_time_threshold_hours": 24,
    "excluded_services": ["cosmetic_consult"],
}

FAKE_INCENTIVE_DECISION = {
    "decision": "offer_incentive",
    "chosen_incentive": "10_percent_discount",
    "reasoning": "test override - policy-compliant discount",
    "rerank_required": True,
}


class RecoveryIncentiveReofferStatusTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

        self.db.add(
            Appointment(
                id=1,
                customer_id=None,
                service="Follow-up Consultation",
                provider="Dr. Lee",
                start_time=datetime(2026, 9, 25, 13, 0),
                duration_minutes=45,
                price=120.0,
                status="available",
            )
        )
        # Queue already exhausted at full price: both candidates have a
        # real prior status, exactly the precondition for the bug.
        self.db.add(
            RecoveryPlanRecord(
                plan_id="plan_test",
                slot_id=1,
                cancelled_by="existing-patient",
                open_slot={
                    "slot_id": 1,
                    "provider": "Dr. Lee",
                    "service_type": "Follow-up Consultation",
                    "start": "2026-09-25T13:00:00",
                    "duration_min": 45,
                    "price": 120.0,
                },
                candidates=[{"patient_id": "p1"}, {"patient_id": "p2"}],
                excluded=[],
                ranked_candidate_ids=["p1", "p2"],
                current_candidate_index=2,  # past the end - queue exhausted
                stage="NORMAL",
                selected_incentive=None,
                status="exhausted",
                candidate_statuses={"p1": "declined", "p2": "expired"},
                revenue_at_risk=120.0,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _reoffer_via_incentive(self):
        """Runs the incentive fallback and immediately declines its first
        offer (p1), so p2 - who already has a stale "expired" status from
        the full-price round - becomes the next re-offered candidate."""
        with patch(
            "app.services.recovery_service.decide_incentive",
            return_value=FAKE_INCENTIVE_DECISION,
        ):
            plan = apply_incentive_decision(self.db, "plan_test", BUSINESS_POLICY)
        self.assertEqual(plan["stage"], "INCENTIVE")
        self.assertEqual(plan["status"], "pending")
        self.assertEqual(plan["candidate_statuses"]["p1"], "offered")
        return plan

    def test_declined_reoffer_clears_stale_status(self):
        self._reoffer_via_incentive()

        plan = record_candidate_response(self.db, "plan_test", "declined")

        self.assertEqual(plan["current_candidate_index"], 1)
        self.assertEqual(plan["candidate_statuses"]["p1"], "declined")
        # The bug: this used to stay "expired" (setdefault kept the stale
        # full-price-round status) instead of reflecting the live re-offer.
        self.assertEqual(plan["candidate_statuses"]["p2"], "offered")
        self.assertEqual(plan["status"], "pending")

        # Subsequent accept still works normally on top of the fix.
        plan = record_candidate_response(self.db, "plan_test", "accepted")
        self.assertEqual(plan["status"], "filled")
        self.assertEqual(plan["candidate_statuses"]["p2"], "accepted")

        booked = self.db.get(Appointment, 1)
        self.assertEqual(booked.status, "booked")
        self.assertEqual(booked.customer_id, "p2")

    def test_timeout_reoffer_clears_stale_status(self):
        self._reoffer_via_incentive()

        plan = record_candidate_response(self.db, "plan_test", "timeout")

        self.assertEqual(plan["current_candidate_index"], 1)
        self.assertEqual(plan["candidate_statuses"]["p1"], "expired")
        self.assertEqual(plan["candidate_statuses"]["p2"], "offered")
        self.assertEqual(plan["status"], "pending")

        # Subsequent decline still works, and correctly exhausts the queue
        # since p2 was the last ranked candidate.
        plan = record_candidate_response(self.db, "plan_test", "declined")
        self.assertEqual(plan["status"], "exhausted")
        self.assertEqual(plan["candidate_statuses"]["p2"], "declined")


if __name__ == "__main__":
    unittest.main()
