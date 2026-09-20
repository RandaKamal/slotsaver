from datetime import datetime
from typing import Any

from pydantic import BaseModel


class VoicePreferenceRequest(BaseModel):
    """What the ElevenLabs save_scheduling_intent tool sends us."""

    patient_id: str
    raw_text: str
    # Earlier conversation the final sentence depends on. Optional.
    context: str | None = None


class PreferenceRecordResponse(BaseModel):
    """What we persisted, combining the raw wording and Kevin's structured result."""

    id: int
    patient_id: str
    raw_text: str
    context: str | None = None
    # pending while Nemotron runs in the background; extracted | failed after.
    status: str = "pending"
    # The extractor returns these as objects, not lists; accept either.
    hard_constraints: dict[str, Any] | list[Any] | None = None
    soft_preferences: dict[str, Any] | list[Any] | None = None
    expiry: str | None = None
    contact_preferences: dict[str, Any] | list[Any] | str | None = None
    notify_if_opens: bool = False
    requested_time: str | None = None
    raw_extraction: dict[str, Any] = {}
    refinement_diff: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
