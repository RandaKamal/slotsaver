"""TEMPORARY in-memory data store standing in for Randa's real DB/services.

Exists only so Kevin's AI routes and the playground page have something to run against
while the database layer isn't ready yet. Delete this once apps/api/app/db + services
are wired up — routes should call real services, not this module.
"""

import uuid

PATIENTS: dict[str, dict] = {
    "patient_A": {
        "patient_id": "patient_A",
        "name": "Alex",
        "soft_preferences": {"preferred_time_ranges": ["morning"], "preferred_provider": None, "provider_flexible": True},
        "earlier_if_possible": False,
        "last_contacted_days_ago": 3,
        "recent_declines": 0,
    },
    "patient_B": {
        "patient_id": "patient_B",
        "name": "Bianca",
        "soft_preferences": {"preferred_time_ranges": ["afternoon"], "preferred_provider": "Dr. Lee", "provider_flexible": False},
        "earlier_if_possible": True,
        "last_contacted_days_ago": 20,
        "recent_declines": 0,
    },
    "patient_C": {
        "patient_id": "patient_C",
        "name": "Chris",
        "soft_preferences": {"preferred_time_ranges": ["evening"], "preferred_provider": None, "provider_flexible": True},
        "earlier_if_possible": False,
        "last_contacted_days_ago": 15,
        "recent_declines": 1,
    },
}

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

# plan_id -> RecoveryPlan-shaped dict
RECOVERY_PLANS: dict[str, dict] = {}


def new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:8]}"
