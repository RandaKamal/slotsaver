import json

from app.agents.nemotron.client import call_nemotron_json
from app.agents.nemotron.prompts import RANKING_SYSTEM_PROMPT


def rank_candidates(open_slot: dict, candidates: list[dict], policies: dict | None = None) -> dict:
    user_prompt = json.dumps(
        {"open_slot": open_slot, "candidates": candidates, "policies": policies or {}}
    )
    return call_nemotron_json(RANKING_SYSTEM_PROMPT, user_prompt)


if __name__ == "__main__":
    open_slot = {
        "appointment_type": "follow-up",
        "provider": "Dr. Lee",
        "start_time": "2026-09-24T14:00:00",
        "duration_minutes": 30,
    }
    candidates = [
        {
            "patient_id": "patient_1",
            "soft_preferences": {
                "preferred_time_ranges": ["afternoon"],
                "preferred_provider": "Dr. Lee",
                "provider_flexible": False,
            },
            "earlier_if_possible": True,
            "last_contacted_days_ago": 12,
            "recent_declines": 0,
        },
        {
            "patient_id": "patient_2",
            "soft_preferences": {
                "preferred_time_ranges": ["morning"],
                "preferred_provider": None,
                "provider_flexible": True,
            },
            "earlier_if_possible": False,
            "last_contacted_days_ago": 1,
            "recent_declines": 2,
        },
        {
            "patient_id": "patient_3",
            "soft_preferences": {
                "preferred_time_ranges": ["afternoon"],
                "preferred_provider": None,
                "provider_flexible": True,
            },
            "earlier_if_possible": True,
            "last_contacted_days_ago": 30,
            "recent_declines": 0,
        },
    ]
    result = rank_candidates(open_slot, candidates)
    print(json.dumps(result, indent=2))
