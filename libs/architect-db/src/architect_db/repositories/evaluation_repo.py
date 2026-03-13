"""EvaluationReport repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select

from architect_common.enums import EvalVerdict
from architect_common.types import TaskId
from architect_db.models.evaluation import EvaluationReport
from architect_db.repositories.base import BaseRepository


class EvaluationReportRepository(BaseRepository[EvaluationReport]):
    """Async repository for :class:`EvaluationReport` entities."""

    model_class = EvaluationReport

    async def get_by_id(self, report_id: str) -> EvaluationReport | None:
        """Return the evaluation report with the given ID, or ``None``.

        Args:
            report_id: The evaluation report primary key.
        """
        return await self._session.get(EvaluationReport, report_id)

    async def get_by_task(self, task_id: TaskId) -> list[EvaluationReport]:
        """Return all evaluation reports for a given task.

        Args:
            task_id: The task primary key.

        Returns:
            A list of :class:`EvaluationReport` rows for the task.
        """
        stmt = (
            select(EvaluationReport)
            .where(EvaluationReport.task_id == str(task_id))
            .order_by(EvaluationReport.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_task(self, task_id: TaskId) -> EvaluationReport | None:
        """Return the most recent evaluation report for a task.

        Args:
            task_id: The task primary key.

        Returns:
            The latest :class:`EvaluationReport` for the task, or ``None``.
        """
        stmt = (
            select(EvaluationReport)
            .where(EvaluationReport.task_id == str(task_id))
            .order_by(EvaluationReport.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_verdict(self, verdict: EvalVerdict) -> list[EvaluationReport]:
        """Return all evaluation reports with a given verdict.

        Args:
            verdict: The evaluation verdict to filter on.

        Returns:
            A list of :class:`EvaluationReport` rows matching the verdict.
        """
        stmt = (
            select(EvaluationReport)
            .where(EvaluationReport.verdict == str(verdict))
            .order_by(EvaluationReport.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
