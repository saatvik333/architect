"""WorldStateLedger ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base


class WorldStateLedger(Base):
    """Versioned world-state snapshot.

    Maps to the ``world_state_ledger`` table.  Uses a ``BIGSERIAL`` primary key
    (``version``) instead of the standard UUID-based id.
    """

    __tablename__ = "world_state_ledger"

    version: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    proposal_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("proposals.id"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<WorldStateLedger version={self.version!r}>"
