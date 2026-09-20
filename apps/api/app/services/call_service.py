"""Places the actual outbound call once an owner approves an OutreachAttempt.

STATUS: written against ElevenLabs' documented outbound-calling shape as of
this writing, but NEVER YET CALLED against a real number - that's blocked on
Twilio account creation and importing the number into ElevenLabs (see
docs/twilio-integration.md). Verify the endpoint path and payload shape
against ElevenLabs' current docs before the first real test; API surfaces
like this change and this has not been exercised end-to-end.

What this is NOT: it does not touch booking logic. ElevenLabs' own
`book_appointment_call` webhook tool (see scripts/update_call_tool_urls.py)
still confirms real availability and does the actual booking during the call.
This only starts the call and hands the agent its brief.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

OUTBOUND_CALL_URL = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"

# The three phone-call tools, from update_call_tool_urls.py - swapped in via
# per-conversation override so the browser widget's client tools (which
# cannot run on a phone call) are never touched.
CALL_TOOL_IDS = [
    "tool_1301m2yb2arne1ztf3jt0js6n6dj",  # get_available_slots_call
    "tool_7201m2yb2x9xecpty0e8z17589m1",  # save_scheduling_intent_call
    "tool_6301m2yb2xj7e1e8z5swnjwapkx0",  # book_appointment_call
]


class CallNotConfigured(Exception):
    """Raised when Twilio/ElevenLabs telephony isn't set up yet."""


def place_call(attempt) -> dict:
    """attempt: an OutreachAttempt row, already approved.

    Raises CallNotConfigured (never a bare exception) if the phone number
    import hasn't happened yet, so the caller can show that plainly instead
    of a stack trace.
    """
    if not attempt.phone_number:
        raise CallNotConfigured(f"No phone number on file for {attempt.patient_id}")

    agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
    phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not phone_number_id:
        raise CallNotConfigured(
            "ELEVENLABS_PHONE_NUMBER_ID is not set - import your Twilio number into "
            "ElevenLabs (Conversational AI -> Phone Numbers) first."
        )

    brief = attempt.call_brief or {}
    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": phone_number_id,
        "to_number": attempt.phone_number,
        "conversation_initiation_client_data": {
            "dynamic_variables": {"patient_id": attempt.patient_id},
            "conversation_config_override": {
                "agent": {
                    "prompt": {"tool_ids": CALL_TOOL_IDS},
                    "first_message": brief.get("opening_line"),
                }
            },
        },
    }

    response = httpx.post(
        OUTBOUND_CALL_URL,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=30.0,
    )
    if response.status_code >= 400:
        logger.error("outbound call failed for attempt %s: %s", attempt.id, response.text)
        response.raise_for_status()

    return response.json()
