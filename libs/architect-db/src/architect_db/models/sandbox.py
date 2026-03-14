"""Sandbox ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class SandboxSession(UUIDPrimaryKeyMixin, Base):
    """Sandbox session record tracking container lifecycle.

    Maps to the ``sandbox_sessions`` table.
    """

    __tablename__ = "sandbox_sessions"

    task_id: Mapped[str | None] = mapped_column(Text, ForeignKey("tasks.id"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="creating", index=True)

    container_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    image: Mapped[str | None] = mapped_column(Text, nullable=True)

    resource_limits: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<SandboxSession id={self.id!r} status={self.status!r}>"


class SandboxAuditLog(UUIDPrimaryKeyMixin, Base):
    """Audit trail for commands executed inside a sandbox.

    Maps to the ``sandbox_audit_log`` table.
    """

    __tablename__ = "sandbox_audit_log"

    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sandbox_sessions.id"), nullable=False, index=True
    )
    command: Mapped[str] = mapped_column(Text, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SandboxAuditLog id={self.id!r} session_id={self.session_id!r}>"
