"""Task ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import AgentType, EvalVerdict, ModelTier, StatusEnum, TaskType
from architect_db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted task in the task graph.

    Maps to the ``tasks`` table.
    """

    __tablename__ = "tasks"

    type: Mapped[str] = mapped_column(
        sa.Enum(TaskType, native_enum=False, length=64), nullable=False
    )
    agent_type: Mapped[str | None] = mapped_column(
        sa.Enum(AgentType, native_enum=False, length=64), nullable=True
    )
    model_tier: Mapped[str | None] = mapped_column(
        sa.Enum(ModelTier, native_enum=False, length=64), nullable=True
    )
    status: Mapped[str] = mapped_column(
        sa.Enum(StatusEnum, native_enum=False, length=64),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dependencies: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    dependents: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    assigned_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_history: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    verdict: Mapped[str | None] = mapped_column(
        sa.Enum(EvalVerdict, native_enum=False, length=64), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Task id={self.id!r} type={self.type!r} status={self.status!r}>"
