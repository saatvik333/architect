"""Event repository for the append-only event log."""

from __future__ import annotations

from sqlalchemy import select

from architect_db.models.event import EventLog
from architect_db.repositories.base import BaseRepository


class EventRepository(BaseRepository[EventLog]):
    """Async repository for :class:`EventLog` entries."""

    model_class = EventLog

    async def append(self, event: EventLog) -> EventLog:
        """Append a new event to the log.

        This is an alias for :meth:`create` with clearer domain semantics.

        Args:
            event: The event log entry to persist.

        Returns:
            The persisted event with any server-generated defaults populated.
        """
        return await self.create(event)

    async def query_by_type(
        self,
        event_type: str,
        *,
        limit: int = 100,
    ) -> list[EventLog]:
        """Return events matching the given type, most recent first.

        Args:
            event_type: The event type string to filter on.
            limit: Maximum number of results.

        Returns:
            A list of matching :class:`EventLog` rows.
        """
        stmt = (
            select(EventLog)
            .where(EventLog.type == event_type)
            .order_by(EventLog.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def query_by_task(
        self,
        task_id: str,
        *,
        limit: int = 100,
    ) -> list[EventLog]:
        """Return events associated with a specific task.

        Args:
            task_id: The task identifier to filter on.
            limit: Maximum number of results.

        Returns:
            A list of matching :class:`EventLog` rows ordered by timestamp.
        """
        stmt = (
            select(EventLog)
            .where(EventLog.task_id == task_id)
            .order_by(EventLog.timestamp.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
