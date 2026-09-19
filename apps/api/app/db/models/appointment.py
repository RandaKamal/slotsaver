"""Appointment slots: seeded/mock availability, booked deterministically.

No AI involved here — availability is whatever rows exist in this table,
and booking is a plain conditional DB update.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # None while the slot is open; set to the booking patient's id once booked.
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    service: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    # "available" | "booked" | "cancelled"
    status: Mapped[str] = mapped_column(String, nullable=False, default="available", index=True)
