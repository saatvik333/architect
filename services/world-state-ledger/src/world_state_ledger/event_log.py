"""Append-only event log backed by PostgreSQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.logging import get_logger
from architect_common.types import AgentId, EventId, TaskId, new_event_id, utcnow
from architect_db.models.event import EventLog as EventLogRow

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(component="world_state_ledger.event_log")


class EventLog:
    """Service-layer wrapper around the ``event_log`` table.

    Provides idempotent appends (via ``idempotency_key``) and filtered queries.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Write ────────────────────────────────────────────────────────

    async def append(self, entry: dict[str, Any]) -> EventId:
        """Insert an event into the log.

        If an ``idempotency_key`` is present and already exists, the insert is
        silently skipped (ON CONFLICT DO NOTHING) and the existing event id is
        returned.

        Args:
            entry: A dict with keys matching :class:`EventLogRow` columns.
                   At minimum ``type`` and ``payload`` should be provided.

        Returns:
            The ``EventId`` of the (possibly pre-existing) event row.
        """
        event_id = entry.get("id") or new_event_id()
        idempotency_key = entry.get("idempotency_key")

        async with self._session_factory() as session:
            # Fast-path: check idempotency_key before inserting.
            if idempotency_key:
                existing = await self._find_by_idempotency_key(session, idempotency_key)
                if existing is not None:
                    logger.debug("idempotent skip", idempotency_key=idempotency_key)
                    return EventId(existing.id)

            row_data = {
                "id": str(event_id),
                "type": entry.get("type", "unknown"),
                "timestamp": entry.get("timestamp", utcnow()),
                "ledger_version": entry.get("ledger_version"),
                "proposal_id": entry.get("proposal_id"),
                "task_id": entry.get("task_id"),
                "agent_id": entry.get("agent_id"),
                "payload": entry.get("payload"),
                "source": entry.get("source", "world-state-ledger"),
                "idempotency_key": idempotency_key,
            }

            stmt = pg_insert(EventLogRow).values(**row_data)
            if idempotency_key:
                stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
            await session.execute(stmt)
            await session.commit()

        logger.info("event appended", event_id=str(event_id), event_type=row_data["type"])
        return EventId(str(event_id))

    # ── Read ─────────────────────────────────────────────────────────

    async def query(
        self,
        *,
        event_type: str | None = None,
        task_id: TaskId | None = None,
        agent_id: AgentId | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return event log entries matching the given filters.

        Results are ordered newest-first.
        """
        async with self._session_factory() as session:
            stmt = select(EventLogRow).order_by(EventLogRow.timestamp.desc())

            if event_type is not None:
                stmt = stmt.where(EventLogRow.type == event_type)
            if task_id is not None:
                stmt = stmt.where(EventLogRow.task_id == str(task_id))
            if agent_id is not None:
                stmt = stmt.where(EventLogRow.agent_id == str(agent_id))

            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            rows: Sequence[EventLogRow] = result.scalars().all()

        return [self._row_to_dict(row) for row in rows]

    async def get_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Fetch a single event by its primary key."""
        async with self._session_factory() as session:
            row = await session.get(EventLogRow, event_id)
            if row is None:
                return None
            return self._row_to_dict(row)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _find_by_idempotency_key(session: AsyncSession, key: str) -> EventLogRow | None:
        stmt = select(EventLogRow).where(EventLogRow.idempotency_key == key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _row_to_dict(row: EventLogRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "type": row.type,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "ledger_version": row.ledger_version,
            "proposal_id": row.proposal_id,
            "task_id": row.task_id,
            "agent_id": row.agent_id,
            "payload": row.payload,
            "source": row.source,
            "idempotency_key": row.idempotency_key,
        }
