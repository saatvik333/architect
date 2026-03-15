"""Specification ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class Specification(UUIDPrimaryKeyMixin, Base):
    """Persisted specification from the Spec Engine.

    Maps to the ``specifications`` table.
    """

    __tablename__ = "specifications"

    intent: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", index=True)

    constraints: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    success_criteria: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    file_targets: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    assumptions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    open_questions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    stakeholder_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scope_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Specification id={self.id!r} status={self.status!r}>"
