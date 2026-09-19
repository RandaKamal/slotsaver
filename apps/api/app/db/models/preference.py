"""Storage for voice-captured scheduling preferences.

This table stores what the voice layer sends and what Kevin's
/api/preferences/extract returns for it — it does no extraction itself.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PreferenceRecord(Base):
    __tablename__ = "preference_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    # Exactly what the patient said, unmodified.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Fields from Kevin's documented /api/preferences/extract contract,
    # pulled out for easy querying.
    hard_constraints: Mapped[list | None] = mapped_column(JSON, nullable=True)
    soft_preferences: Mapped[list | None] = mapped_column(JSON, nullable=True)
    expiry: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_preferences: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # The full response body Kevin's endpoint returned, verbatim, so nothing
    # is lost if his actual response shape has extra/different fields.
    raw_extraction: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
