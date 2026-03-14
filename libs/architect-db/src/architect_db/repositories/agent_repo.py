"""AgentSession repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select, update

from architect_common.enums import StatusEnum
from architect_common.types import AgentId, TaskId
from architect_db.models.agent import AgentSession
from architect_db.repositories.base import BaseRepository


class AgentSessionRepository(BaseRepository[AgentSession]):
    """Async repository for :class:`AgentSession` entities."""

    model_class = AgentSession

    async def get_by_id(self, agent_id: str) -> AgentSession | None:
        """Return the agent session with the given ID, or ``None``.

        Args:
            agent_id: The agent session primary key.
        """
        return await self._session.get(AgentSession, str(agent_id))

    async def get_active_sessions(self) -> list[AgentSession]:
        """Return all agent sessions currently running.

        Returns:
            A list of :class:`AgentSession` rows with ``running`` status.
        """
        stmt = (
            select(AgentSession)
            .where(AgentSession.status == StatusEnum.RUNNING)
            .order_by(AgentSession.started_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_task(self, task_id: TaskId) -> list[AgentSession]:
        """Return all agent sessions associated with a given task.

        Args:
            task_id: The task primary key.

        Returns:
            A list of :class:`AgentSession` rows for the task.
        """
        stmt = (
            select(AgentSession)
            .where(AgentSession.current_task == str(task_id))
            .order_by(AgentSession.started_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        agent_id: AgentId,
        status: StatusEnum,
    ) -> AgentSession:
        """Update the status of an agent session.

        Args:
            agent_id: The agent session primary key.
            status: The new status value.

        Returns:
            The updated :class:`AgentSession` instance.

        Raises:
            ValueError: If the agent session does not exist.
        """
        stmt = (
            update(AgentSession).where(AgentSession.id == str(agent_id)).values(status=str(status))
        )
        await self._session.execute(stmt)
        await self._session.flush()

        updated = await self.get_by_id(agent_id)
        if updated is None:
            msg = f"AgentSession {agent_id!r} not found"
            raise ValueError(msg)
        return updated
