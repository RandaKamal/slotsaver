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
