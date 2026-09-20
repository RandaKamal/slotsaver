"""Business Profile Setup: configure the one active business (dental clinic,
tutoring center, barber shop, ...) the rest of the app schedules for.

Reading `/active` is what appointment_service, recovery_matcher,
recovery_scheduler, outreach_service and the voice tools already do (via
app.services.business_profile_service) to resolve working hours, worker/
service lists, booking rules and incentive policy instead of hardcoded
clinic constants. This router is the CRUD surface the settings page and the
profile switcher call.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.business_profile import (
    BusinessProfileCreate,
    BusinessProfileDetail,
    BusinessProfileSummary,
    BusinessProfileUpdate,
)
from app.services.business_profile_service import (
    activate_profile,
    create_profile,
    get_active_profile,
    get_profile,
    list_profiles,
    update_profile,
)

router = APIRouter(prefix="/api/business-profiles", tags=["business-profiles"])


@router.get("", response_model=list[BusinessProfileSummary])
def list_business_profiles(db: Session = Depends(get_db)) -> list[BusinessProfileSummary]:
    return [BusinessProfileSummary.model_validate(p) for p in list_profiles(db)]


@router.get("/active", response_model=BusinessProfileDetail)
def get_active_business_profile(db: Session = Depends(get_db)) -> BusinessProfileDetail:
    return BusinessProfileDetail.model_validate(get_active_profile(db))


@router.get("/{profile_id}", response_model=BusinessProfileDetail)
def get_business_profile(profile_id: int, db: Session = Depends(get_db)) -> BusinessProfileDetail:
    return BusinessProfileDetail.model_validate(get_profile(db, profile_id))


@router.post("", response_model=BusinessProfileDetail)
def create_business_profile(
    payload: BusinessProfileCreate, db: Session = Depends(get_db)
) -> BusinessProfileDetail:
    return BusinessProfileDetail.model_validate(create_profile(db, payload.model_dump()))


@router.patch("/{profile_id}", response_model=BusinessProfileDetail)
def update_business_profile(
    profile_id: int, payload: BusinessProfileUpdate, db: Session = Depends(get_db)
) -> BusinessProfileDetail:
    patch = payload.model_dump(exclude_unset=True)
    return BusinessProfileDetail.model_validate(update_profile(db, profile_id, patch))


@router.post("/{profile_id}/activate", response_model=BusinessProfileDetail)
def activate_business_profile(
    profile_id: int, db: Session = Depends(get_db)
) -> BusinessProfileDetail:
    return BusinessProfileDetail.model_validate(activate_profile(db, profile_id))
