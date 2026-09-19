from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.mock_store import PATIENTS
from app.agents.nemotron.preference_extractor import extract_preferences

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class ExtractRequest(BaseModel):
    transcript: str
    patient_id: str


@router.post("/extract")
def extract(payload: ExtractRequest) -> dict:
    result = extract_preferences(payload.transcript, payload.patient_id)
    if payload.patient_id in PATIENTS:
        PATIENTS[payload.patient_id]["soft_preferences"] = result.get("soft_preferences", {})
        PATIENTS[payload.patient_id]["earlier_if_possible"] = result.get("earlier_if_possible", False)
    return result
