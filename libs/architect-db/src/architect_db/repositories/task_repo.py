"""Task repository with domain-specific query methods."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from architect_db.models.task import Task
from architect_db.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Async repository for :class:`Task` entities."""

    model_class = Task

    async def list_by_status(
        self,
        status: str,
        *,
        limit: int = 100,
    ) -> list[Task]:
        """Return tasks matching the given status.

        Args:
            status: The status string to filter on (e.g. ``"pending"``).
            limit: Maximum number of results.

        Returns:
            A list of matching :class:`Task` rows.
        """
        stmt = (
            select(Task)
            .where(Task.status == status)
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        task_id: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        """Transition a task to a new status.

        Also sets ``started_at`` when transitioning to ``"running"`` and
        ``completed_at`` when transitioning to a terminal state.

        Args:
            task_id: The task primary key.
            status: The new status value.
            error_message: Optional error message for failed tasks.
        """
        values: dict[str, object] = {"status": status}

        if error_message is not None:
            values["error_message"] = error_message

        now = datetime.now(UTC)
        if status == "running":
            values["started_at"] = now
        elif status in {"completed", "failed", "cancelled"}:
            values["completed_at"] = now

        stmt = update(Task).where(Task.id == task_id).values(**values)
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_next_pending(self) -> Task | None:
        """Return the highest-priority pending task whose dependencies are all met.

        This performs a simple query for pending tasks ordered by descending
        priority and ascending creation time.  Dependency resolution should be
        handled at the service layer; this method returns the first candidate.

        Returns:
            The next :class:`Task` to execute, or ``None`` if the queue is empty.
        """
        stmt = (
            select(Task)
            .where(Task.status == "pending")
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
