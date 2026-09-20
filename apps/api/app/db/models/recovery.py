"""Durable home for the RecoveryPlan shape Kevin's /api/recovery/* routes
already build as plain dicts (see app/agents/mock_store.py's RECOVERY_PLANS).

This does not introduce a new recovery concept - it's the same plan_id,
open_slot, candidates, ranked_candidate_ids, current_candidate_index, stage,
selected_incentive, status fields, given a row instead of an in-memory dict
that's lost on restart. cancelled_by/excluded/revenue_at_risk mirror the
extra fields /api/recovery/from-cancellation already returns.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryPlanRecord(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    slot_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Patient who held the booking that was cancelled to free this slot.
    cancelled_by: Mapped[str | None] = mapped_column(String, nullable=True)

    open_slot: Mapped[dict] = mapped_column(JSON, nullable=False)
    candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    excluded: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ranked_candidate_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    current_candidate_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # "NORMAL" | "INCENTIVE"
    stage: Mapped[str] = mapped_column(String, nullable=False, default="NORMAL")
    selected_incentive: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # "pending" | "filled" | "exhausted" | "ranking_failed"
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    revenue_at_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
