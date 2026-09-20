"""Reads back what actually happened on a placed call, so the recovery queue
advances on the call's real outcome instead of a blind timeout.

Before this, a candidate saying "no" on the phone reached nothing: the offer
sat until candidate_timeout_seconds elapsed before anyone else was tried,
and the system could not tell "they declined ten seconds in" from "it is
still ringing".

How the outcome is decided, in order:

1. The call must be OVER. ElevenLabs reports that per conversation; a call
   still in progress is left alone rather than guessed at.
2. If the slot is booked to this candidate, they accepted - the phone agent's
   own book_appointment_call tool did that during the call, so this is a fact
   in our own database, not an inference from a transcript.
3. Otherwise the call ended without a booking, which is a decline.

Deliberately NOT a model call. Whether someone booked is something we know
exactly, and putting Nemotron in this path would mean a rate limit could
silently strand the queue - the one failure mode this module exists to
remove.
"""

import logging
import os

import httpx

from app.agents.nemotron.client import call_nemotron_json

logger = logging.getLogger(__name__)

_CONVERSATION_URL = "https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}"

# ElevenLabs conversation statuses that mean "not finished yet". Anything else
# (done, failed, and any status added later) is treated as over, so a call
# that ends in a way we have not seen before still releases the queue instead
# of pinning it open forever.
_IN_PROGRESS = {"initiated", "in-progress", "in_progress", "processing"}


class CallStatusUnavailable(Exception):
    """ElevenLabs could not be asked (no key, network, unexpected response).

    Raised rather than assumed-finished: treating an unreachable API as "the
    call ended" would advance the queue while someone is still on the phone.
    """


def call_has_ended(conversation_id: str) -> bool:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise CallStatusUnavailable("ELEVENLABS_API_KEY is not set")

    try:
        response = httpx.get(
            _CONVERSATION_URL.format(conversation_id=conversation_id),
            headers={"xi-api-key": api_key},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise CallStatusUnavailable(f"could not reach ElevenLabs: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        raise CallStatusUnavailable(f"ElevenLabs returned {response.status_code}")

    status = (response.json() or {}).get("status")
    if not status:
        raise CallStatusUnavailable("conversation has no status field")
    return status not in _IN_PROGRESS


def fetch_transcript(conversation_id: str) -> list[dict]:
    """The finished call's turns, as [{"role": ..., "message": ...}, ...].

    Raises CallStatusUnavailable for the same reasons call_has_ended does -
    an unreadable transcript must not be mistaken for an empty one, because
    an empty transcript reads as "they never agreed to anything".
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise CallStatusUnavailable("ELEVENLABS_API_KEY is not set")

    try:
        response = httpx.get(
            _CONVERSATION_URL.format(conversation_id=conversation_id),
            headers={"xi-api-key": api_key},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise CallStatusUnavailable(f"could not reach ElevenLabs: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        raise CallStatusUnavailable(f"ElevenLabs returned {response.status_code}")

    turns = (response.json() or {}).get("transcript")
    if turns is None:
        raise CallStatusUnavailable("conversation has no transcript field")
    return [
        {"role": turn.get("role") or "", "message": turn.get("message") or ""}
        for turn in turns
        if turn.get("message")
    ]


def caller_accepted(conversation_id: str) -> bool:
    """Did the person on the phone agree to take the slot?

    This exists because the agent's own book_appointment_call tool is a
    WEBHOOK: ElevenLabs calls it from their cloud, so it only reaches a
    publicly routable backend. Running the demo on a laptop means that tool
    fails, the agent says so on the call, and a customer who said "yes, book
    it" ended up with nothing booked - the slot stayed open and the queue
    treated them as a decline.

    So acceptance is read back from what was actually SAID, and the booking
    is made server-side. That also means a webhook that fails for any other
    reason (deploy, timeout, 500) can no longer lose a booking the customer
    already agreed to.

    Unlike the rest of this module this IS a model call - "did they agree"
    is a genuine language question, not a fact we hold. It is contained:
    any failure returns False, which is exactly the behavior that existed
    before this function, so a rate limit degrades to today's outcome
    instead of stranding the queue.
    """
    try:
        turns = fetch_transcript(conversation_id)
    except CallStatusUnavailable as exc:
        logger.info("no transcript for %s: %s", conversation_id, exc)
        return False
    if not turns:
        return False

    dialogue = "\n".join(f"{t['role']}: {t['message']}" for t in turns)
    try:
        verdict = call_nemotron_json(
            system_prompt=(
                "You read one phone call between a clinic's scheduling agent and a "
                "customer who was offered an open appointment slot. Decide only whether "
                "the CUSTOMER agreed to take that slot. Agreeing means a clear yes - "
                "'yes', 'book it', 'that works', 'I'll take it'. Anything else is not "
                "agreement: declining, hedging, asking to be called back, wanting to "
                "check first, or the call ending before they answered. If the agent "
                "said the booking failed but the customer had already agreed, that is "
                "still agreement - you are judging the customer, not the system. "
                'Reply with only {"accepted": true} or {"accepted": false}.'
            ),
            user_prompt=dialogue,
        )
    except Exception:
        logger.exception("could not classify call outcome for %s", conversation_id)
        return False

    return bool((verdict or {}).get("accepted"))
