"""Human Interface repository with escalation and approval gate queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update

from architect_db.models.escalation import ApprovalGate, ApprovalVote, Escalation
from architect_db.repositories.base import BaseRepository


class EscalationRepository(BaseRepository[Escalation]):
    """Async repository for :class:`Escalation` entities."""

    model_class = Escalation

    async def get_pending(self, *, limit: int = 100) -> list[Escalation]:
        stmt = (
            select(Escalation)
            .where(Escalation.status == "pending")
            .order_by(Escalation.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(
        self, status: str, *, limit: int = 100, offset: int = 0
    ) -> list[Escalation]:
        stmt = (
            select(Escalation)
            .where(Escalation.status == status)
            .order_by(Escalation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_task(self, task_id: str) -> list[Escalation]:
        stmt = (
            select(Escalation)
            .where(Escalation.source_task_id == task_id)
            .order_by(Escalation.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def resolve(
        self,
        escalation_id: str,
        *,
        resolved_by: str,
        resolution: str,
        resolution_details: dict[str, object] | None = None,
        resolved_at: datetime | None = None,
    ) -> Escalation | None:
        stmt = (
            update(Escalation)
            .where(Escalation.id == escalation_id)
            .values(
                status="resolved",
                resolved_by=resolved_by,
                resolution=resolution,
                resolution_details=resolution_details,
                resolved_at=resolved_at or func.now(),
            )
            .returning(Escalation)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalars().first()

    async def get_expired_pending(self) -> list[Escalation]:
        stmt = select(Escalation).where(
            Escalation.status == "pending",
            Escalation.expires_at.isnot(None),
            Escalation.expires_at < func.now(),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self) -> dict[str, int]:
        from sqlalchemy import case

        stmt = select(
            func.count().label("total"),
            func.count(case((Escalation.status == "pending", 1))).label("pending"),
            func.count(case((Escalation.status == "resolved", 1))).label("resolved"),
        ).select_from(Escalation)

        result = await self._session.execute(stmt)
        row = result.one()
        total = row.total or 0
        pending = row.pending or 0
        resolved = row.resolved or 0
        return {
            "total": total,
            "pending": pending,
            "resolved": resolved,
            "expired": total - pending - resolved,
        }


class ApprovalGateRepository(BaseRepository[ApprovalGate]):
    """Async repository for :class:`ApprovalGate` entities."""

    model_class = ApprovalGate

    async def get_pending(
        self, *, limit: int = 100, action_type: str | None = None
    ) -> list[ApprovalGate]:
        stmt = (
            select(ApprovalGate)
            .where(ApprovalGate.status == "pending")
            .order_by(ApprovalGate.created_at.desc())
            .limit(limit)
        )
        if action_type is not None:
            stmt = stmt.where(ApprovalGate.action_type == action_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self, *, limit: int = 100, offset: int = 0, action_type: str | None = None
    ) -> list[ApprovalGate]:
        stmt = (
            select(ApprovalGate)
            .order_by(ApprovalGate.created_at.desc())
            .limit(min(limit, 1000))
            .offset(offset)
        )
        if action_type is not None:
            stmt = stmt.where(ApprovalGate.action_type == action_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_resource(self, resource_id: str) -> list[ApprovalGate]:
        stmt = (
            select(ApprovalGate)
            .where(ApprovalGate.resource_id == resource_id)
            .order_by(ApprovalGate.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ApprovalVoteRepository(BaseRepository[ApprovalVote]):
    """Async repository for :class:`ApprovalVote` entities."""

    model_class = ApprovalVote

    async def get_by_gate(self, gate_id: str) -> list[ApprovalVote]:
        stmt = (
            select(ApprovalVote)
            .where(ApprovalVote.gate_id == gate_id)
            .order_by(ApprovalVote.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
