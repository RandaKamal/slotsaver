"""Connects the voice layer to Kevin's existing preference-extraction API.

This module does no extraction of its own: it forwards raw text to
POST {BACKEND_BASE_URL}/api/preferences/extract (Kevin's Nemotron-backed
endpoint) and persists whatever structured result comes back, alongside the
original wording.
"""

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.preference import PreferenceRecord

EXTRACT_PATH = "/api/preferences/extract"


def extract_preferences(patient_id: str, raw_text: str) -> dict:
    """Calls Kevin's /api/preferences/extract with its actual contract
    (transcript, patient_id) and returns its JSON response unmodified."""

    settings = get_settings()
    if not settings.backend_base_url:
        raise HTTPException(
            status_code=500,
            detail="BACKEND_BASE_URL is not set — cannot reach the preference extraction API.",
        )

    url = settings.backend_base_url.rstrip("/") + EXTRACT_PATH
    try:
        response = httpx.post(
            url,
            json={"transcript": raw_text, "patient_id": patient_id},
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach preference extraction API at {url}: {exc}",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Preference extraction API returned {response.status_code} "
                f"from {url}: {response.text}"
            ),
        )

    return response.json()


def save_preference_record(
    db: Session, patient_id: str, raw_text: str, extracted: dict
) -> PreferenceRecord:
    """Persists the raw wording plus Kevin's structured result, verbatim."""

    record = PreferenceRecord(
        patient_id=patient_id,
        raw_text=raw_text,
        hard_constraints=extracted.get("hard_constraints"),
        soft_preferences=extracted.get("soft_preferences"),
        # The extractor emits "valid_until"/"contact_preference" (singular);
        # keep this table's column names but read the real keys.
        expiry=extracted.get("valid_until"),
        contact_preferences=extracted.get("contact_preference"),
        raw_extraction=extracted,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
