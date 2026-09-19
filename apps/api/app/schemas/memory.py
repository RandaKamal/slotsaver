from datetime import datetime
from typing import Any

from pydantic import BaseModel


class VoicePreferenceRequest(BaseModel):
    """What the ElevenLabs save_scheduling_intent tool sends us."""

    patient_id: str
    raw_text: str


class PreferenceRecordResponse(BaseModel):
    """What we persisted, combining the raw wording and Kevin's structured result."""

    id: int
    patient_id: str
    raw_text: str
    # The extractor returns these as objects, not lists; accept either.
    hard_constraints: dict[str, Any] | list[Any] | None = None
    soft_preferences: dict[str, Any] | list[Any] | None = None
    expiry: str | None = None
    contact_preferences: dict[str, Any] | list[Any] | str | None = None
    raw_extraction: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
