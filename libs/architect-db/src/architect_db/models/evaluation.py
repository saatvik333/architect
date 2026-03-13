"""EvaluationReport ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from architect_db.models.base import Base, UUIDPrimaryKeyMixin


class EvaluationReport(UUIDPrimaryKeyMixin, Base):
    """Evaluation result for a task execution.

    Maps to the ``evaluation_reports`` table.
    """

    __tablename__ = "evaluation_reports"

    task_id: Mapped[str] = mapped_column(Text, ForeignKey("tasks.id"), nullable=False, index=True)
    sandbox_session_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("sandbox_sessions.id"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    layers_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layer_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    score: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EvaluationReport id={self.id!r} task_id={self.task_id!r} verdict={self.verdict!r}>"
        )
