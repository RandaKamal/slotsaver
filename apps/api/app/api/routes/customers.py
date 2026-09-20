"""Read-only view of everyone SlotSaver has stored scheduling intent for -
the "Patients" (or Students/Clients, per the active business profile) tab.

Backs onto the same PreferenceRecord rows and patient_memory.py brief-
building the voice agent and recovery ranking already use - this is not a
separate customer database, just a listing over the one that exists.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.db.models.preference import PreferenceRecord
from app.db.session import get_db
from app.services.patient_memory import summarise_for_log

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
def list_customers(db: Session = Depends(get_db)) -> list[dict]:
    patient_ids = list(
        db.execute(
            select(PreferenceRecord.patient_id).distinct().order_by(PreferenceRecord.patient_id)
        ).scalars()
    )
    return [summarise_for_log(db, patient_id) for patient_id in patient_ids]
