"""The clinic's incentive policy - what Nemotron's incentive decision (see
app/agents/nemotron/incentive.py) is allowed to choose from, and what
recovery_service's deterministic backstop checks it against. A config
constant, not demo state, so it lives here rather than in mock_store.
"""

BUSINESS_POLICY: dict = {
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
