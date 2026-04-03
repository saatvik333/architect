"""Failure Taxonomy ORM models for failure records, post-mortems, and improvements."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import FailureCode, ImprovementType
from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class FailureRecord(UUIDPrimaryKeyMixin, Base):
    """Classified failure from evaluation or agent execution.

    Maps to the ``failure_records`` table.
    """

    __tablename__ = "failure_records"

    task_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    failure_code: Mapped[str] = mapped_column(
        sa.Enum(FailureCode, native_enum=False, length=64), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)

    eval_layer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    classified_by: Mapped[str] = mapped_column(Text, nullable=False, default="auto")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<FailureRecord id={self.id!r} code={self.failure_code!r} resolved={self.resolved!r}>"
        )


class PostMortem(UUIDPrimaryKeyMixin, Base):
    """Post-mortem analysis run for a project or task.

    Maps to the ``post_mortems`` table.
    """

    __tablename__ = "post_mortems"

    project_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    root_causes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    prompt_improvements: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    new_adversarial_tests: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    heuristic_updates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    topology_recommendations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PostMortem id={self.id!r} project={self.project_id!r} status={self.status!r}>"


class Improvement(UUIDPrimaryKeyMixin, Base):
    """Improvement proposal generated from post-mortem analysis.

    Maps to the ``improvements`` table.
    """

    __tablename__ = "improvements"

    post_mortem_id: Mapped[str] = mapped_column(
        Text,
        sa.ForeignKey("post_mortems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    improvement_type: Mapped[str] = mapped_column(
        sa.Enum(ImprovementType, native_enum=False, length=64), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Improvement id={self.id!r} type={self.improvement_type!r} applied={self.applied!r}>"
        )


class SimulationRun(UUIDPrimaryKeyMixin, Base):
    """Simulation training run record.

    Maps to the ``simulation_runs`` table.
    """

    __tablename__ = "simulation_runs"

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    failures_injected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failures_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detection_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SimulationRun id={self.id!r} source={self.source_type!r} status={self.status!r}>"
