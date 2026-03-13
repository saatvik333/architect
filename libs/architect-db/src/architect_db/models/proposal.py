"""Proposal ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class Proposal(UUIDPrimaryKeyMixin, Base):
    """State mutation proposal record.

    Maps to the ``proposals`` table.
    """

    __tablename__ = "proposals"

    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    mutations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    verdict: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    verdict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ledger_version_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ledger_version_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<Proposal id={self.id!r} verdict={self.verdict!r}>"
