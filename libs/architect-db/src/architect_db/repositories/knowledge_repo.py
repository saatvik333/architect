"""Knowledge & Memory repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select, update

from architect_db.models.knowledge import (
    HeuristicRule,
    KnowledgeEntry,
    KnowledgeObservation,
    MetaStrategy,
)
from architect_db.repositories.base import BaseRepository


class KnowledgeEntryRepository(BaseRepository[KnowledgeEntry]):
    """Async repository for :class:`KnowledgeEntry` entities."""

    model_class = KnowledgeEntry

    async def get_by_layer(
        self, layer: str, *, limit: int = 100, offset: int = 0
    ) -> list[KnowledgeEntry]:
        stmt = (
            select(KnowledgeEntry)
            .where(KnowledgeEntry.layer == layer, KnowledgeEntry.is_active.is_(True))
            .order_by(KnowledgeEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_topic(self, topic: str, *, limit: int = 100) -> list[KnowledgeEntry]:
        stmt = (
            select(KnowledgeEntry)
            .where(KnowledgeEntry.topic == topic, KnowledgeEntry.is_active.is_(True))
            .order_by(KnowledgeEntry.usage_count.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active(self, *, limit: int = 100, offset: int = 0) -> list[KnowledgeEntry]:
        stmt = (
            select(KnowledgeEntry)
            .where(KnowledgeEntry.is_active.is_(True))
            .order_by(KnowledgeEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def increment_usage(self, entry_id: str) -> None:
        stmt = (
            update(KnowledgeEntry)
            .where(KnowledgeEntry.id == entry_id)
            .values(usage_count=KnowledgeEntry.usage_count + 1)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def deactivate(self, entry_id: str) -> None:
        stmt = update(KnowledgeEntry).where(KnowledgeEntry.id == entry_id).values(is_active=False)
        await self._session.execute(stmt)
        await self._session.flush()


class KnowledgeObservationRepository(BaseRepository[KnowledgeObservation]):
    """Async repository for :class:`KnowledgeObservation` entities."""

    model_class = KnowledgeObservation

    async def get_uncompressed(
        self, *, domain: str | None = None, limit: int = 500
    ) -> list[KnowledgeObservation]:
        stmt = select(KnowledgeObservation).where(KnowledgeObservation.compressed_into.is_(None))
        if domain is not None:
            stmt = stmt.where(KnowledgeObservation.context["domain"].as_string() == domain)
        stmt = stmt.order_by(KnowledgeObservation.created_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_compressed(self, observation_ids: list[str], pattern_id: str) -> None:
        stmt = (
            update(KnowledgeObservation)
            .where(KnowledgeObservation.id.in_(observation_ids))
            .values(compressed_into=pattern_id)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class HeuristicRuleRepository(BaseRepository[HeuristicRule]):
    """Async repository for :class:`HeuristicRule` entities."""

    model_class = HeuristicRule

    async def get_active_by_domain(self, domain: str, *, limit: int = 50) -> list[HeuristicRule]:
        stmt = (
            select(HeuristicRule)
            .where(HeuristicRule.domain == domain, HeuristicRule.is_active.is_(True))
            .order_by(HeuristicRule.success_rate.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active(self, *, limit: int = 100) -> list[HeuristicRule]:
        stmt = (
            select(HeuristicRule)
            .where(HeuristicRule.is_active.is_(True))
            .order_by(HeuristicRule.hit_count.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_outcome(self, rule_id: str, *, success: bool) -> None:
        rule = await self.get_by_id(rule_id)
        if rule is None:
            return
        new_hits = rule.hit_count + 1
        successes = int(rule.success_rate * rule.hit_count) + (1 if success else 0)
        new_rate = successes / new_hits if new_hits > 0 else 0.0
        stmt = (
            update(HeuristicRule)
            .where(HeuristicRule.id == rule_id)
            .values(hit_count=new_hits, success_rate=new_rate)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class MetaStrategyRepository(BaseRepository[MetaStrategy]):
    """Async repository for :class:`MetaStrategy` entities."""

    model_class = MetaStrategy

    async def get_by_status(self, status: str, *, limit: int = 50) -> list[MetaStrategy]:
        stmt = (
            select(MetaStrategy)
            .where(MetaStrategy.status == status)
            .order_by(MetaStrategy.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
