"""Human Interface ORM models for escalations and approval gates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class Escalation(UUIDPrimaryKeyMixin, Base):
    """Human-facing decision escalation.

    Maps to the ``escalations`` table.
    """

    __tablename__ = "escalations"

    source_agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)

    options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    recommended_option: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_if_wrong: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", index=True)
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    decision_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_security_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_impact_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Escalation id={self.id!r} status={self.status!r} severity={self.severity!r}>"


class ApprovalGate(UUIDPrimaryKeyMixin, Base):
    """Approval gate requiring human sign-off before proceeding.

    Maps to the ``approval_gates`` table.
    """

    __tablename__ = "approval_gates"

    action_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", index=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ApprovalGate id={self.id!r} type={self.action_type!r} status={self.status!r}>"


class ApprovalVote(UUIDPrimaryKeyMixin, Base):
    """Individual vote on an approval gate.

    Maps to the ``approval_votes`` table.
    """

    __tablename__ = "approval_votes"

    gate_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    voter: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ApprovalVote id={self.id!r} gate={self.gate_id!r} decision={self.decision!r}>"
