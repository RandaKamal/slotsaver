"""One configurable business profile per demo vertical (dental clinic,
tutoring center, barber shop, ...). Everything the scheduling, recovery,
voice and incentive code used to assume about "a clinic" - working hours,
provider/service lists, booking limits, recovery timeouts, incentive policy -
lives here as one DB row instead of scattered module-level constants.

Workers and services are stored as JSON lists rather than their own tables:
`appointments.provider`/`.service` stay free-text, so no migration of the
existing appointment data is needed, and the whole profile can be read or
replaced in one query. Exactly one profile has `active=True` at a time; that
is the profile every other part of the app reads through
`services.business_profile_service.get_active_profile`.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    business_type: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    timezone: Mapped[str] = mapped_column(String, nullable=False, default="America/New_York")
    location: Mapped[str] = mapped_column(String, nullable=False, default="")

    # UI vocabulary. Kept on the profile (not a business_type -> label switch
    # in frontend code) so a new vertical needs a new row, not a new build.
    worker_label: Mapped[str] = mapped_column(String, nullable=False, default="Provider")
    customer_label: Mapped[str] = mapped_column(String, nullable=False, default="Customer")
    service_label: Mapped[str] = mapped_column(String, nullable=False, default="Service")

    # ["mon","tue",...] and "HH:MM" 24h strings.
    working_days: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    open_time: Mapped[str] = mapped_column(String, nullable=False, default="09:00")
    close_time: Mapped[str] = mapped_column(String, nullable=False, default="17:00")

    # [{id, name, role, service_ids: [...], working_days: [...],
    #   start_time, end_time, breaks: [{start,end}], active}]
    workers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # [{id, name, duration_minutes, price, eligible_roles: [...],
    #   buffer_minutes, allow_provider_preference}]
    services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # {min_notice_minutes, max_horizon_days, same_day_allowed,
    #  customer_can_choose_provider, provider_flexibility_allowed}
    booking_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # {auto_recovery_enabled, candidate_timeout_seconds, max_recovery_attempts,
    #  incentive_fallback_enabled}
    recovery_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Same shape recovery_service/incentive.py already consume:
    # {max_discount_percent, minimum_revenue, allowed_incentives: [...],
    #  incentive_time_threshold_hours, excluded_services: [...],
    #  incentive_score_threshold}
    incentive_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
