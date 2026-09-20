"""Two decisions that sit between "we ranked a candidate" and "a call happens":

- decide_outreach(): is this call worth placing at all? A candidate existing
  in the ranking is not consent to call them - this can say no.
- generate_call_brief(): if yes, what should the voice agent actually say?
  Tone and talking points only; ElevenLabs' own tools still confirm real
  availability and do the actual booking.

Neither of these places a call. See app/services/outreach_service.py for the
approval queue that sits between this decision and an actual dial-out.
"""

import json

from app.agents.nemotron.client import call_nemotron_json
from app.agents.nemotron.prompts import CALL_BRIEF_SYSTEM_PROMPT, OUTREACH_DECISION_SYSTEM_PROMPT


def decide_outreach(
    open_slot: dict,
    candidate: dict,
    match_score: float,
    incentive: dict | None,
    contact_history: dict,
    business_policy: dict,
) -> dict:
    """Returns {"should_call": bool, "reason": str}."""
    payload = {
        "open_slot": open_slot,
        "candidate": candidate,
        "match_score": match_score,
        "incentive": incentive,
        "contact_history": contact_history,
        "business_policy": business_policy,
    }
    return call_nemotron_json(OUTREACH_DECISION_SYSTEM_PROMPT, json.dumps(payload))


def generate_call_brief(open_slot: dict, patient_intent: dict, incentive: dict | None) -> dict:
    """Returns {"tone", "opening_line", "key_points", "incentive_pitch"}."""
    payload = {"open_slot": open_slot, "patient_intent": patient_intent, "incentive": incentive}
    return call_nemotron_json(CALL_BRIEF_SYSTEM_PROMPT, json.dumps(payload))
