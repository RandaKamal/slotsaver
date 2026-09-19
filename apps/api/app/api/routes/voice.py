from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.memory import PreferenceRecordResponse, VoicePreferenceRequest
from app.services.preference_service import extract_preferences, save_preference_record

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/preferences", response_model=PreferenceRecordResponse)
def save_scheduling_intent(
    payload: VoicePreferenceRequest, db: Session = Depends(get_db)
) -> PreferenceRecordResponse:
    """Called by the ElevenLabs `save_scheduling_intent` tool.

    Forwards the raw wording to Kevin's /api/preferences/extract and stores
    both the wording and the structured result it returns.
    """

    extracted = extract_preferences(payload.patient_id, payload.raw_text)
    record = save_preference_record(db, payload.patient_id, payload.raw_text, extracted)
    return PreferenceRecordResponse.model_validate(record)
