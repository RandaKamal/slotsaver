import json

from app.agents.nemotron.client import call_nemotron_json
from app.agents.nemotron.prompts import INCENTIVE_SYSTEM_PROMPT


def decide_incentive(open_slot: dict, business_policy: dict, decline_history: list[dict]) -> dict:
    user_prompt = json.dumps(
        {
            "open_slot": open_slot,
            "business_policy": business_policy,
            "decline_history": decline_history,
        }
    )
    return call_nemotron_json(INCENTIVE_SYSTEM_PROMPT, user_prompt)


if __name__ == "__main__":
    open_slot = {
        "appointment_type": "follow-up",
        "provider": "Dr. Lee",
        "start_time": "2026-09-19T18:00:00",
        "duration_minutes": 30,
        "price": 120,
        "hours_until_appointment": 3,
    }
    business_policy = {
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
    decline_history = [
        {"patient_id": "patient_A", "response": "declined"},
        {"patient_id": "patient_B", "response": "timeout"},
        {"patient_id": "patient_C", "response": "declined"},
    ]
    result = decide_incentive(open_slot, business_policy, decline_history)
    print(json.dumps(result, indent=2))
