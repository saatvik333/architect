"""Failure Taxonomy repositories for failure records, post-mortems, and improvements."""

from __future__ import annotations

from sqlalchemy import func, select, update

from architect_db.models.failure import (
    FailureRecord,
    Improvement,
    PostMortem,
    SimulationRun,
)
from architect_db.repositories.base import BaseRepository


class FailureRecordRepository(BaseRepository[FailureRecord]):
    """Async repository for :class:`FailureRecord` entities."""

    model_class = FailureRecord

    async def get_by_task(self, task_id: str) -> list[FailureRecord]:
        stmt = (
            select(FailureRecord)
            .where(FailureRecord.task_id == task_id)
            .order_by(FailureRecord.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_project(self, project_id: str, *, limit: int = 100) -> list[FailureRecord]:
        stmt = (
            select(FailureRecord)
            .where(FailureRecord.project_id == project_id)
            .order_by(FailureRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(self, failure_code: str, *, limit: int = 100) -> list[FailureRecord]:
        stmt = (
            select(FailureRecord)
            .where(FailureRecord.failure_code == failure_code)
            .order_by(FailureRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_unresolved(self, *, limit: int = 100) -> list[FailureRecord]:
        stmt = (
            select(FailureRecord)
            .where(FailureRecord.resolved.is_(False))
            .order_by(FailureRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats_by_code(self) -> dict[str, int]:
        stmt = select(
            FailureRecord.failure_code,
            func.count().label("cnt"),
        ).group_by(FailureRecord.failure_code)
        result = await self._session.execute(stmt)
        return {row.failure_code: row.cnt for row in result.all()}

    async def get_recent(self, *, limit: int = 50) -> list[FailureRecord]:
        stmt = select(FailureRecord).order_by(FailureRecord.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PostMortemRepository(BaseRepository[PostMortem]):
    """Async repository for :class:`PostMortem` entities."""

    model_class = PostMortem

    async def get_by_project(self, project_id: str, *, limit: int = 100) -> list[PostMortem]:
        stmt = (
            select(PostMortem)
            .where(PostMortem.project_id == project_id)
            .order_by(PostMortem.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self) -> PostMortem | None:
        stmt = select(PostMortem).order_by(PostMortem.created_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ImprovementRepository(BaseRepository[Improvement]):
    """Async repository for :class:`Improvement` entities."""

    model_class = Improvement

    async def get_by_post_mortem(self, post_mortem_id: str) -> list[Improvement]:
        stmt = (
            select(Improvement)
            .where(Improvement.post_mortem_id == post_mortem_id)
            .order_by(Improvement.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_unapplied(self, *, limit: int = 100) -> list[Improvement]:
        stmt = (
            select(Improvement)
            .where(Improvement.applied.is_(False))
            .order_by(Improvement.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_applied(self, improvement_id: str) -> Improvement | None:
        stmt = (
            update(Improvement)
            .where(Improvement.id == improvement_id)
            .values(applied=True, applied_at=func.now())
            .returning(Improvement)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalars().first()


class SimulationRunRepository(BaseRepository[SimulationRun]):
    """Async repository for :class:`SimulationRun` entities."""

    model_class = SimulationRun

    async def get_by_status(self, status: str, *, limit: int = 100) -> list[SimulationRun]:
        stmt = (
            select(SimulationRun)
            .where(SimulationRun.status == status)
            .order_by(SimulationRun.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, *, limit: int = 50) -> list[SimulationRun]:
        stmt = select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
