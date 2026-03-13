"""SandboxSession repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select

from architect_common.enums import SandboxStatus
from architect_common.types import TaskId
from architect_db.models.sandbox import SandboxAuditLog, SandboxSession
from architect_db.repositories.base import BaseRepository


class SandboxSessionRepository(BaseRepository[SandboxSession]):
    """Async repository for :class:`SandboxSession` entities."""

    model_class = SandboxSession

    async def get_by_id(self, session_id: str) -> SandboxSession | None:
        """Return the sandbox session with the given ID, or ``None``.

        Args:
            session_id: The sandbox session primary key.
        """
        return await self._session.get(SandboxSession, session_id)

    async def get_active(self) -> list[SandboxSession]:
        """Return all currently active sandbox sessions.

        Active sessions are those in ``creating``, ``ready``, or ``running`` status.

        Returns:
            A list of active :class:`SandboxSession` rows.
        """
        active_statuses = [
            SandboxStatus.CREATING,
            SandboxStatus.READY,
            SandboxStatus.RUNNING,
        ]
        stmt = (
            select(SandboxSession)
            .where(SandboxSession.status.in_([str(s) for s in active_statuses]))
            .order_by(SandboxSession.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_task(self, task_id: TaskId) -> list[SandboxSession]:
        """Return all sandbox sessions associated with a given task.

        Args:
            task_id: The task primary key.

        Returns:
            A list of :class:`SandboxSession` rows for the task.
        """
        stmt = (
            select(SandboxSession)
            .where(SandboxSession.task_id == str(task_id))
            .order_by(SandboxSession.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_audit_log(self, session_id: str) -> list[SandboxAuditLog]:
        """Return all audit log entries for a sandbox session.

        Args:
            session_id: The sandbox session primary key.

        Returns:
            A list of :class:`SandboxAuditLog` rows ordered by execution time.
        """
        stmt = (
            select(SandboxAuditLog)
            .where(SandboxAuditLog.session_id == session_id)
            .order_by(SandboxAuditLog.executed_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
