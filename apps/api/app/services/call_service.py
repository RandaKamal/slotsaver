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

# Phone calls use a SEPARATE agent from the browser widget.
#
# The original plan was one agent with a per-conversation tool_ids override,
# but that does not work: ElevenLabs rejects overrides referencing tools not
# already attached to the agent ("Tool IDs not attached to this agent"), and
# the browser SDK's override type has no tool_ids field at all - only prompt
# and llm. Attaching all six tools to one agent would expose the webhook trio
# to the browser widget, where they point at a URL ElevenLabs cannot reach
# during local development.
#
# So: ELEVENLABS_AGENT_ID keeps the three client tools for the browser, and
# ELEVENLABS_PHONE_AGENT_ID carries the three webhook tools for telephony.
# Same prompt and voice on both; only the tool transport differs.


class CallNotConfigured(Exception):
    """Raised when Twilio/ElevenLabs telephony isn't set up yet."""


def _dynamic_variables(attempt, slot: dict | None, patient_brief: str | None = None) -> dict:
    """Call context the phone agent's prompt interpolates.

    Without these the agent knows it is on a call but not why, and falls back
    to behaving like an inbound receptionist - asking the patient what they
    want when we are the ones who called them with news.
    """
    brief = attempt.call_brief or {}
    slot = slot or {}
    points = brief.get("key_points") or []
    incentive = attempt.incentive or {}
    pitch = brief.get("incentive_pitch")
    return {
        "patient_id": attempt.patient_id,
        "slot_id": str(attempt.slot_id),
        "slot_provider": slot.get("provider", "the clinic"),
        "slot_service": slot.get("service_type", "an appointment"),
        "slot_when": slot.get("start", "the opened slot"),
        "call_key_points": chr(10).join(f"- {p}" for p in points)
        if points
        else "- They asked to be told if this slot opened up.",
        "call_tone": f"- Keep the call {brief.get('tone', 'warm')} in tone.",
        "patient_history": patient_brief or "No previous conversations on file for this patient.",
        # "if they hesitate" meant an authorised incentive was almost never
        # actually spoken: the agent held it back waiting for pushback that a
        # short call never produces, so a discount the business had already
        # approved went unmentioned. When one is authorised it is part of the
        # offer, so say it up front.
        # Both the incentive and the booking-confirmation instruction ride in
        # incentive_line because the agent's prompt only interpolates a fixed
        # set of placeholders, and this is one of them - a new variable would
        # be accepted by the API and then silently ignored.
        "incentive_line": " ".join(
            filter(
                None,
                [
                    (
                        f"IMPORTANT - an incentive is approved for this call and you must "
                        f"mention it proactively, in your first or second sentence, without "
                        f"waiting for them to hesitate or object: {pitch}"
                        if pitch
                        else "No incentive is authorised on this call. Do not offer a discount."
                    ),
                    # The booking tool is a WEBHOOK, so it only reaches a
                    # publicly routable backend - it fails whenever this runs
                    # anywhere else, and the agent was announcing that failure
                    # to the customer ("the booking didn't go through on my
                    # end"). The booking is NOT lost when that happens:
                    # recovery_scheduler reads the transcript back and makes
                    # it server-side within seconds. So a customer who agreed
                    # really is booked, and telling them otherwise is both
                    # alarming and wrong.
                    "BOOKING - when they agree to take the slot, confirm it warmly and "
                    "plainly: tell them it is booked and will show up on their calendar. "
                    "Never tell the customer the booking failed, did not go through, or "
                    "that you will call back to confirm it, and never mention tools, "
                    "systems or errors. Their agreement is recorded the moment they give "
                    "it and the appointment is created from this call, whatever any tool "
                    "reports back to you.",
                ],
            )
        ),
    }


def place_call(attempt, slot: dict | None = None, patient_brief: str | None = None) -> dict:
    """attempt: an OutreachAttempt row, already approved.

    Raises CallNotConfigured (never a bare exception) if the phone number
    import hasn't happened yet, so the caller can show that plainly instead
    of a stack trace.

    DEMO_CALL_OVERRIDE_NUMBER redirects every outbound call to one fixed
    number regardless of whose record triggered it. This isn't a hack around
    real behavior - a Twilio trial account can only dial numbers you've
    verified, so during the demo every "call the patient" has to reach the
    one verified number (yours) no matter which seeded patient was matched.
    Unset in a real deployment with a paid Twilio number.
    """
    to_number = os.environ.get("DEMO_CALL_OVERRIDE_NUMBER") or attempt.phone_number
    if not to_number:
        raise CallNotConfigured(f"No phone number on file for {attempt.patient_id}")

    agent_id = os.environ.get("ELEVENLABS_PHONE_AGENT_ID")
    if not agent_id:
        raise CallNotConfigured(
            "ELEVENLABS_PHONE_AGENT_ID is not set - phone calls need the telephony "
            "agent (webhook tools), not the browser agent."
        )
    phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not phone_number_id:
        raise CallNotConfigured(
            "ELEVENLABS_PHONE_NUMBER_ID is not set - import your Twilio number into "
            "ElevenLabs (Conversational AI -> Phone Numbers) first."
        )

    brief = attempt.call_brief or {}

    # An approved incentive goes into the FIRST MESSAGE, not just the prompt.
    # Prompt instructions are advice the agent can interpret away - it did
    # exactly that, holding the discount back for an objection that never
    # came. The opening line is spoken verbatim, so putting it here is the
    # only way to guarantee an authorised discount is actually said out loud.
    opening_line = brief.get("opening_line") or ""
    incentive_pitch = brief.get("incentive_pitch")
    if incentive_pitch and incentive_pitch.strip().lower() not in opening_line.lower():
        opening_line = f"{opening_line.rstrip()} {incentive_pitch.strip()}".strip()

    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": {
            "dynamic_variables": _dynamic_variables(attempt, slot, patient_brief),
            "conversation_config_override": {
                # No tool override: the phone agent already carries exactly the
                # webhook tools a call needs.
                "agent": {"first_message": opening_line}
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
