"""AgentSession ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_common.enums import AgentType, ModelTier, StatusEnum
from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class AgentSession(UUIDPrimaryKeyMixin, Base):
    """Persisted agent session record.

    Maps to the ``agent_sessions`` table.
    """

    __tablename__ = "agent_sessions"

    agent_type: Mapped[str] = mapped_column(
        sa.Enum(AgentType, native_enum=False, length=64), nullable=False
    )
    model_tier: Mapped[str] = mapped_column(
        sa.Enum(ModelTier, native_enum=False, length=64), nullable=False
    )
    current_task: Mapped[str | None] = mapped_column(Text, ForeignKey("tasks.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(StatusEnum, native_enum=False, length=64),
        nullable=False,
        default="running",
        index=True,
    )
    tokens_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AgentSession id={self.id!r} agent_type={self.agent_type!r} status={self.status!r}>"
        )
