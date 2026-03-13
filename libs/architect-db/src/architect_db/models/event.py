"""EventLog ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class EventLog(UUIDPrimaryKeyMixin, Base):
    """Append-only event log entry.

    Maps to the ``event_log`` table.
    """

    __tablename__ = "event_log"

    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    ledger_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    proposal_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)

    def __repr__(self) -> str:
        return f"<EventLog id={self.id!r} type={self.type!r}>"
