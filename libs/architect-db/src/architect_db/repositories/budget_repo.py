"""Economic Governor repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select

from architect_db.models.budget import AgentEfficiency, BudgetRecord, EnforcementAction
from architect_db.repositories.base import BaseRepository


class BudgetRecordRepository(BaseRepository[BudgetRecord]):
    """Async repository for :class:`BudgetRecord` entities."""

    model_class = BudgetRecord

    async def get_latest_by_project(self, project_id: str) -> BudgetRecord | None:
        stmt = (
            select(BudgetRecord)
            .where(BudgetRecord.project_id == project_id)
            .order_by(BudgetRecord.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_project(self, project_id: str, *, limit: int = 100) -> list[BudgetRecord]:
        stmt = (
            select(BudgetRecord)
            .where(BudgetRecord.project_id == project_id)
            .order_by(BudgetRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AgentEfficiencyRepository(BaseRepository[AgentEfficiency]):
    """Async repository for :class:`AgentEfficiency` entities."""

    model_class = AgentEfficiency

    async def get_latest_by_agent(self, agent_id: str) -> AgentEfficiency | None:
        stmt = (
            select(AgentEfficiency)
            .where(AgentEfficiency.agent_id == agent_id)
            .order_by(AgentEfficiency.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_leaderboard(self, *, limit: int = 50) -> list[AgentEfficiency]:
        stmt = (
            select(AgentEfficiency).order_by(AgentEfficiency.efficiency_score.desc()).limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class EnforcementActionRepository(BaseRepository[EnforcementAction]):
    """Async repository for :class:`EnforcementAction` entities."""

    model_class = EnforcementAction

    async def get_by_level(
        self, level: str, *, limit: int = 100, offset: int = 0
    ) -> list[EnforcementAction]:
        stmt = (
            select(EnforcementAction)
            .where(EnforcementAction.enforcement_level == level)
            .order_by(EnforcementAction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, *, limit: int = 50) -> list[EnforcementAction]:
        stmt = select(EnforcementAction).order_by(EnforcementAction.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
