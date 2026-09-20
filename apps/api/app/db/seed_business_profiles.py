"""Seeds the three demo business profiles (dental clinic, tutoring center,
barber shop) the first time the app boots against an empty
business_profiles table. Dental is active by default so the existing clinic
demo keeps working unchanged; switching the active profile from the
settings page changes services, worker labels, hours and policy without a
code change or restart.

Idempotent: only inserts when the table has zero rows, so it never clobbers
a profile edited through the API.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.business_profile import BusinessProfile

_DENTAL = dict(
    slug="dental-clinic",
    name="Riverside Dental",
    business_type="dental_clinic",
    active=True,
    timezone="America/New_York",
    location="412 Maple Ave, Springdale",
    worker_label="Dentist",
    customer_label="Patient",
    service_label="Treatment",
    working_days=["mon", "tue", "wed", "thu", "fri"],
    open_time="08:00",
    close_time="18:00",
    workers=[
        {"id": "dr-lee", "name": "Dr. Lee", "role": "Dentist", "service_ids": ["cleaning", "consult", "followup"], "working_days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "08:00", "end_time": "17:00", "breaks": [{"start": "12:00", "end": "13:00"}], "active": True},
        {"id": "dr-patel", "name": "Dr. Patel", "role": "Hygienist", "service_ids": ["cleaning", "followup"], "working_days": ["mon", "tue", "wed", "thu"], "start_time": "09:00", "end_time": "18:00", "breaks": [{"start": "13:00", "end": "13:30"}], "active": True},
    ],
    services=[
        {"id": "cleaning", "name": "Cleaning", "duration_minutes": 45, "price": 120.0, "eligible_roles": ["Dentist", "Hygienist"], "buffer_minutes": 10, "allow_provider_preference": True},
        {"id": "consult", "name": "Consultation", "duration_minutes": 30, "price": 90.0, "eligible_roles": ["Dentist"], "buffer_minutes": 5, "allow_provider_preference": True},
        {"id": "followup", "name": "Follow-up", "duration_minutes": 30, "price": 80.0, "eligible_roles": ["Dentist", "Hygienist"], "buffer_minutes": 5, "allow_provider_preference": False},
    ],
    booking_rules={
        "min_notice_minutes": 60,
        "max_horizon_days": 60,
        "same_day_allowed": True,
        "customer_can_choose_provider": True,
        "provider_flexibility_allowed": True,
    },
    recovery_rules={
        "auto_recovery_enabled": True,
        "candidate_timeout_seconds": 25,
        "max_recovery_attempts": 5,
        "incentive_fallback_enabled": True,
    },
    incentive_policy={
        "max_discount_percent": 20,
        "minimum_revenue": 60,
        "allowed_incentives": [
            {"id": "10_percent_discount", "type": "percent_discount", "value": 10},
            {"id": "future_credit_10", "type": "fixed_credit", "value": 10},
            {"id": "referral_offer_15", "type": "referral_offer", "value": 15},
        ],
        "incentive_time_threshold_hours": 24,
        "excluded_services": ["cosmetic_consult"],
        "incentive_score_threshold": 0.9,
    },
)

_TUTORING = dict(
    slug="tutoring-center",
    name="Bright Path Learning Center",
    business_type="learning_center",
    active=False,
    timezone="America/New_York",
    location="88 College St, Springdale",
    worker_label="Tutor",
    customer_label="Student",
    service_label="Session",
    working_days=["mon", "tue", "wed", "thu", "fri", "sat"],
    open_time="14:00",
    close_time="20:00",
    workers=[
        {"id": "tutor-nguyen", "name": "Ms. Nguyen", "role": "Tutor", "service_ids": ["math", "examprep"], "working_days": ["mon", "wed", "fri"], "start_time": "14:00", "end_time": "19:00", "breaks": [], "active": True},
        {"id": "tutor-osei", "name": "Mr. Osei", "role": "Tutor", "service_ids": ["physics", "examprep"], "working_days": ["tue", "thu", "sat"], "start_time": "15:00", "end_time": "20:00", "breaks": [], "active": True},
    ],
    services=[
        {"id": "math", "name": "Math Tutoring", "duration_minutes": 60, "price": 45.0, "eligible_roles": ["Tutor"], "buffer_minutes": 0, "allow_provider_preference": True},
        {"id": "physics", "name": "Physics Tutoring", "duration_minutes": 60, "price": 50.0, "eligible_roles": ["Tutor"], "buffer_minutes": 0, "allow_provider_preference": True},
        {"id": "examprep", "name": "Exam Prep", "duration_minutes": 90, "price": 70.0, "eligible_roles": ["Tutor"], "buffer_minutes": 15, "allow_provider_preference": True},
    ],
    booking_rules={
        "min_notice_minutes": 120,
        "max_horizon_days": 30,
        "same_day_allowed": False,
        "customer_can_choose_provider": True,
        "provider_flexibility_allowed": True,
    },
    recovery_rules={
        "auto_recovery_enabled": True,
        "candidate_timeout_seconds": 40,
        "max_recovery_attempts": 3,
        "incentive_fallback_enabled": False,
    },
    incentive_policy={
        "max_discount_percent": 15,
        "minimum_revenue": 30,
        "allowed_incentives": [
            {"id": "session_discount_10", "type": "percent_discount", "value": 10},
        ],
        "incentive_time_threshold_hours": 12,
        "excluded_services": ["examprep"],
        "incentive_score_threshold": 0.85,
    },
)

_BARBER = dict(
    slug="barber-shop",
    name="Fade District Barbershop",
    business_type="barber_shop",
    active=False,
    timezone="America/New_York",
    location="19 Union St, Springdale",
    worker_label="Barber",
    customer_label="Client",
    service_label="Service",
    working_days=["tue", "wed", "thu", "fri", "sat"],
    open_time="10:00",
    close_time="19:00",
    workers=[
        {"id": "barber-james", "name": "James", "role": "Barber", "service_ids": ["haircut", "combo"], "working_days": ["tue", "wed", "thu", "fri", "sat"], "start_time": "10:00", "end_time": "18:00", "breaks": [{"start": "14:00", "end": "14:30"}], "active": True},
        {"id": "barber-alicia", "name": "Alicia", "role": "Barber", "service_ids": ["haircut", "beard", "combo"], "working_days": ["wed", "thu", "fri", "sat"], "start_time": "11:00", "end_time": "19:00", "breaks": [], "active": True},
    ],
    services=[
        {"id": "haircut", "name": "Haircut", "duration_minutes": 30, "price": 35.0, "eligible_roles": ["Barber"], "buffer_minutes": 5, "allow_provider_preference": True},
        {"id": "beard", "name": "Beard Trim", "duration_minutes": 15, "price": 20.0, "eligible_roles": ["Barber"], "buffer_minutes": 5, "allow_provider_preference": True},
        {"id": "combo", "name": "Haircut + Beard", "duration_minutes": 45, "price": 50.0, "eligible_roles": ["Barber"], "buffer_minutes": 10, "allow_provider_preference": True},
    ],
    booking_rules={
        "min_notice_minutes": 30,
        "max_horizon_days": 21,
        "same_day_allowed": True,
        "customer_can_choose_provider": True,
        "provider_flexibility_allowed": True,
    },
    recovery_rules={
        "auto_recovery_enabled": True,
        "candidate_timeout_seconds": 15,
        "max_recovery_attempts": 6,
        "incentive_fallback_enabled": True,
    },
    incentive_policy={
        "max_discount_percent": 25,
        "minimum_revenue": 15,
        "allowed_incentives": [
            {"id": "walkin_discount_15", "type": "percent_discount", "value": 15},
            {"id": "loyalty_credit_5", "type": "fixed_credit", "value": 5},
        ],
        "incentive_time_threshold_hours": 6,
        "excluded_services": [],
        "incentive_score_threshold": 0.9,
    },
)

_DEMO_PROFILES = [_DENTAL, _TUTORING, _BARBER]


def seed_business_profiles(db: Session) -> list[str]:
    """Inserts the demo profiles if the table is empty. Returns the slugs
    inserted, for the same startup log line pattern as db/migrate.py."""
    existing = db.execute(select(func.count()).select_from(BusinessProfile)).scalar_one()
    if existing:
        return []

    for data in _DEMO_PROFILES:
        db.add(BusinessProfile(**data))
    db.commit()

    inserted = [p["slug"] for p in _DEMO_PROFILES]
    for slug in inserted:
        print(f"[db] seeded business profile {slug}")
    return inserted
