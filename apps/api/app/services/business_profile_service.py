"""CRUD and lookup for business profiles, plus the accessors the rest of the
app uses instead of the old hardcoded clinic constants:
`get_business_policy` replaces `core/business_policy.BUSINESS_POLICY`, and
`get_time_of_day_ranges` replaces the two copies of `_TIME_OF_DAY_RANGES`.

Exactly one profile is active at a time; activating one deactivates the rest
in the same transaction so callers never observe zero or two active rows.
"""

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.business_hours import TimeOfDayRanges, compute_time_of_day_ranges
from app.db.models.business_profile import BusinessProfile

# Keys recovery_service._incentive_within_policy and agents/nemotron/incentive.py
# already read from the policy dict. Missing keys fall back to these so an
# incomplete profile can't silently disable the incentive gate.
_DEFAULT_INCENTIVE_POLICY = {
    "max_discount_percent": 20,
    "minimum_revenue": 60,
    "allowed_incentives": [],
    "incentive_time_threshold_hours": 24,
    "excluded_services": [],
    "incentive_score_threshold": 0.9,
}

_DEFAULT_BOOKING_RULES = {
    "min_notice_minutes": 60,
    "max_horizon_days": 60,
    "same_day_allowed": True,
    "customer_can_choose_provider": True,
    "provider_flexibility_allowed": True,
}

_DEFAULT_RECOVERY_RULES = {
    "auto_recovery_enabled": True,
    # Whether a candidate is actually dialed without an owner clicking
    # Approve first - the business owner's opt-in this whole automatic
    # workflow depends on. Off by default: a business that hasn't reviewed
    # its incentive policy shouldn't wake up to the system autonomously
    # discounting appointments and cold-calling its customer list.
    "auto_call_enabled": False,
    "candidate_timeout_seconds": 25,
    "max_recovery_attempts": 5,
    "incentive_fallback_enabled": True,
    # Which offer in the queue is the first allowed to carry a discount.
    # 1 = sweeten immediately, 2 = ask the best match at full price and start
    # discounting from the second person onward, a large number = never until
    # the whole queue is exhausted (the original fallback-only behavior).
    # Whatever it authorizes is still capped by incentive_policy.
    "incentive_from_attempt": 2,
}


def list_profiles(db: Session) -> list[BusinessProfile]:
    return list(db.execute(select(BusinessProfile).order_by(BusinessProfile.id)).scalars())


def get_profile(db: Session, profile_id: int) -> BusinessProfile:
    profile = db.get(BusinessProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No such business profile: {profile_id}")
    return profile


def get_active_profile(db: Session) -> BusinessProfile:
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.active.is_(True))
    ).scalars().first()
    if profile is None:
        raise HTTPException(status_code=500, detail="No active business profile configured")
    return profile


def activate_profile(db: Session, profile_id: int) -> BusinessProfile:
    profile = get_profile(db, profile_id)
    db.execute(update(BusinessProfile).values(active=False))
    profile.active = True
    db.commit()
    db.refresh(profile)
    return profile


def create_profile(db: Session, data: dict) -> BusinessProfile:
    profile = BusinessProfile(**data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


_PATCHABLE_FIELDS = {
    "name",
    "business_type",
    "timezone",
    "location",
    "worker_label",
    "customer_label",
    "service_label",
    "working_days",
    "open_time",
    "close_time",
    "workers",
    "services",
    "booking_rules",
    "recovery_rules",
    "incentive_policy",
}


def update_profile(db: Session, profile_id: int, patch: dict) -> BusinessProfile:
    profile = get_profile(db, profile_id)
    for field, value in patch.items():
        if field in _PATCHABLE_FIELDS and value is not None:
            setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


def get_business_policy(db: Session) -> dict:
    """The active profile's incentive policy, same shape the deterministic
    incentive gate (recovery_service) and Nemotron's incentive prompt already
    expect - callers of the old BUSINESS_POLICY constant are unaffected."""
    profile = get_active_profile(db)
    return {**_DEFAULT_INCENTIVE_POLICY, **(profile.incentive_policy or {})}


def get_booking_rules(db: Session) -> dict:
    profile = get_active_profile(db)
    return {**_DEFAULT_BOOKING_RULES, **(profile.booking_rules or {})}


def get_recovery_rules(db: Session) -> dict:
    profile = get_active_profile(db)
    return {**_DEFAULT_RECOVERY_RULES, **(profile.recovery_rules or {})}


def get_time_of_day_ranges(db: Session) -> TimeOfDayRanges:
    profile = get_active_profile(db)
    return compute_time_of_day_ranges(profile.open_time, profile.close_time)
