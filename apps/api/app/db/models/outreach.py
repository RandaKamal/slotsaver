"""An outbound recovery call, from decision through owner approval to outcome.

One row per candidate SlotSaver considers calling about a freed slot. Created
in 'pending_approval' the moment Nemotron decides the call is worth making;
nothing dials out until an owner approves it (see routes/outreach.py).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutreachAttempt(Base):
    __tablename__ = "outreach_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    slot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)

    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_at_risk: Mapped[float] = mapped_column(Float, nullable=False)

    # Nemotron's "is this call worth placing" verdict, kept even for rows that
    # never became a call - this is the audit trail for that decision.
    should_call: Mapped[bool] = mapped_column(nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)

    # None if no incentive was needed - a perfect-fit patient doesn't need one.
    incentive: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # What Nemotron wants ElevenLabs to actually say on this call: tone,
    # opening line, key points, how to raise the incentive if any.
    call_brief: Mapped[dict] = mapped_column(JSON, nullable=False)

    # pending_approval -> approved | rejected -> (approved only) placed | failed
    # -> (placed only) completed_accepted | completed_declined, set once the
    # call itself has finished and its outcome has been read back.
    status: Mapped[str] = mapped_column(String, default="pending_approval", nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)  # owner identity, once we have one

    # ElevenLabs' id for the placed call. Returned by the outbound-call API and
    # kept so the call's OUTCOME can be read back when it ends (see
    # call_outcome.py) - without it a finished call is indistinguishable from
    # one still ringing, and the queue can only advance on a blind timeout.
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
