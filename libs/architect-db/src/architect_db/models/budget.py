"""Economic Governor ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import AgentType, EnforcementLevel, ModelTier
from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class BudgetRecord(UUIDPrimaryKeyMixin, Base):
    """Point-in-time budget snapshot for a project.

    Maps to the ``budget_records`` table.
    """

    __tablename__ = "budget_records"

    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    allocated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allocated_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    consumed_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    burn_rate_tokens_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    enforcement_level: Mapped[str] = mapped_column(
        sa.Enum(EnforcementLevel, native_enum=False, length=64),
        nullable=False,
        default="none",
    )

    phase_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<BudgetRecord id={self.id!r} project={self.project_id!r}>"


class AgentEfficiency(UUIDPrimaryKeyMixin, Base):
    """Per-agent efficiency score over a time window.

    Maps to the ``agent_efficiency_scores`` table.
    """

    __tablename__ = "agent_efficiency_scores"

    agent_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(
        sa.Enum(AgentType, native_enum=False, length=64), nullable=False
    )
    model_tier: Mapped[str] = mapped_column(
        sa.Enum(ModelTier, native_enum=False, length=64), nullable=False
    )

    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    efficiency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AgentEfficiency id={self.id!r} agent={self.agent_id!r} score={self.efficiency_score}>"


class EnforcementAction(UUIDPrimaryKeyMixin, Base):
    """Audit log of enforcement actions taken by the Economic Governor.

    Maps to the ``enforcement_actions`` table.
    """

    __tablename__ = "enforcement_actions"

    enforcement_level: Mapped[str] = mapped_column(
        sa.Enum(EnforcementLevel, native_enum=False, length=64), nullable=False
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    budget_consumed_pct: Mapped[float] = mapped_column(Float, nullable=False)

    reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EnforcementAction id={self.id!r} type={self.action_type!r}>"
