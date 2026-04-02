"""Agent efficiency scoring.

Computes a per-agent efficiency metric defined as:

    efficiency = (tasks_completed * quality_score) / max(tokens_consumed, 1)

Scores are normalised to [0, 1] across the leaderboard and ranked.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import AgentType, ModelTier
from architect_common.logging import get_logger
from architect_common.types import AgentId, utcnow
from architect_db.models.budget import AgentEfficiency
from economic_governor.models import AgentEfficiencyScore, EfficiencyLeaderboard

logger = get_logger(component="economic_governor.efficiency_scorer")


class _AgentStats:
    """Mutable accumulator for per-agent statistics."""

    __slots__ = (
        "agent_type",
        "cost_usd",
        "model_tier",
        "quality_sum",
        "tasks_completed",
        "tasks_failed",
        "tokens_consumed",
    )

    def __init__(
        self,
        agent_type: AgentType = AgentType.CODER,
        model_tier: ModelTier = ModelTier.TIER_2,
    ) -> None:
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.quality_sum: float = 0.0
        self.tokens_consumed: int = 0
        self.cost_usd: float = 0.0
        self.agent_type: AgentType = agent_type
        self.model_tier: ModelTier = model_tier


class EfficiencyScorer:
    """Accumulates per-agent task outcomes and produces ranked efficiency scores."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agents: dict[str, _AgentStats] = {}
        self._cached_leaderboard: EfficiencyLeaderboard | None = None
        self._lock = asyncio.Lock()

    # ── Data ingestion ───────────────────────────────────────────────

    async def record_task_completed(
        self,
        agent_id: AgentId,
        quality_score: float,
        tokens: int,
        cost_usd: float,
        agent_type: AgentType | None = None,
        model_tier: ModelTier | None = None,
    ) -> None:
        """Record a successful task completion for an agent."""
        async with self._lock:
            stats = self._get_or_create(agent_id)
            stats.tasks_completed += 1
            stats.quality_sum += quality_score
            stats.tokens_consumed += tokens
            stats.cost_usd += cost_usd
            if agent_type is not None:
                stats.agent_type = agent_type
            if model_tier is not None:
                stats.model_tier = model_tier
            self._cached_leaderboard = None

    async def record_task_failed(
        self,
        agent_id: AgentId,
        tokens: int,
        cost_usd: float,
        agent_type: AgentType | None = None,
        model_tier: ModelTier | None = None,
    ) -> None:
        """Record a failed task attempt for an agent."""
        async with self._lock:
            stats = self._get_or_create(agent_id)
            stats.tasks_failed += 1
            stats.tokens_consumed += tokens
            stats.cost_usd += cost_usd
            if agent_type is not None:
                stats.agent_type = agent_type
            if model_tier is not None:
                stats.model_tier = model_tier
            self._cached_leaderboard = None

    # ── Scoring ──────────────────────────────────────────────────────

    async def compute_scores(self) -> EfficiencyLeaderboard:
        """Compute and rank efficiency scores for all tracked agents.

        Returns:
            An :class:`EfficiencyLeaderboard` with entries sorted by efficiency
            (highest first).
        """
        async with self._lock:
            raw_scores: list[tuple[str, float, float, _AgentStats]] = []

            for agent_id, stats in self._agents.items():
                avg_quality = (
                    stats.quality_sum / stats.tasks_completed if stats.tasks_completed > 0 else 0.0
                )
                raw_eff = (stats.tasks_completed * avg_quality) / max(stats.tokens_consumed, 1)
                raw_scores.append((agent_id, raw_eff, avg_quality, stats))

            # Sort descending by raw efficiency.
            raw_scores.sort(key=lambda x: x[1], reverse=True)

            # Normalise to [0, 1].
            max_eff = raw_scores[0][1] if raw_scores else 1.0
            if max_eff <= 0:
                max_eff = 1.0

            entries: list[AgentEfficiencyScore] = []
            for rank, (agent_id, raw_eff, avg_quality, stats) in enumerate(raw_scores, start=1):
                entries.append(
                    AgentEfficiencyScore(
                        agent_id=AgentId(agent_id),
                        efficiency_score=round(raw_eff / max_eff, 4),
                        tasks_completed=stats.tasks_completed,
                        tasks_failed=stats.tasks_failed,
                        quality_score=round(avg_quality, 4),
                        tokens_consumed=stats.tokens_consumed,
                        cost_usd=round(stats.cost_usd, 6),
                        rank=rank,
                    )
                )

            leaderboard = EfficiencyLeaderboard(entries=entries, computed_at=utcnow())
            self._cached_leaderboard = leaderboard
            return leaderboard

    async def get_agent_score(self, agent_id: AgentId) -> AgentEfficiencyScore:
        """Return the efficiency score for a single agent.

        Uses the cached leaderboard when available to avoid recomputing
        on every single-agent lookup.

        If the agent has no recorded stats, returns a zeroed-out score.
        """
        leaderboard = self._cached_leaderboard or await self.compute_scores()
        for entry in leaderboard.entries:
            if entry.agent_id == agent_id:
                return entry

        # Agent not tracked -- return a default entry.
        return AgentEfficiencyScore(
            agent_id=agent_id,
            efficiency_score=0.0,
            rank=len(leaderboard.entries) + 1,
        )

    async def persist_scores(self, leaderboard: EfficiencyLeaderboard) -> None:
        """Persist computed efficiency scores to the ``agent_efficiency_scores`` table."""
        if self._session_factory is None:
            logger.info(
                "skipping score persistence — no session factory",
                agent_count=len(leaderboard.entries),
            )
            return
        try:
            now = leaderboard.computed_at
            window_start = now - timedelta(hours=1)
            async with self._session_factory() as session:
                for entry in leaderboard.entries:
                    stats = self._agents.get(str(entry.agent_id))
                    row = AgentEfficiency(
                        agent_id=str(entry.agent_id),
                        agent_type=stats.agent_type if stats else AgentType.CODER,
                        model_tier=stats.model_tier if stats else ModelTier.TIER_2,
                        tasks_completed=entry.tasks_completed,
                        tasks_failed=entry.tasks_failed,
                        total_tokens_consumed=entry.tokens_consumed,
                        total_cost_usd=entry.cost_usd,
                        average_quality_score=entry.quality_score,
                        efficiency_score=entry.efficiency_score,
                        window_start=window_start,
                        window_end=now,
                    )
                    session.add(row)
                await session.commit()
            logger.info(
                "efficiency scores persisted",
                agent_count=len(leaderboard.entries),
                computed_at=str(now),
            )
        except Exception:
            logger.warning("failed to persist efficiency scores", exc_info=True)

    @classmethod
    async def load_persisted_scores(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> EfficiencyScorer:
        """Create an :class:`EfficiencyScorer` and restore agent stats from the DB.

        Loads the most recent :class:`AgentEfficiency` row per agent and
        populates the in-memory accumulators.  Returns a fresh scorer if the
        query fails or yields no rows.
        """
        scorer = cls(session_factory=session_factory)
        try:
            async with session_factory() as session:
                # SQL-level dedup: subquery finds the max created_at per agent,
                # then we join to fetch only those rows.
                latest_subq = (
                    select(
                        AgentEfficiency.agent_id,
                        func.max(AgentEfficiency.created_at).label("max_created"),
                    )
                    .group_by(AgentEfficiency.agent_id)
                    .subquery()
                )
                stmt = (
                    select(AgentEfficiency)
                    .join(
                        latest_subq,
                        (AgentEfficiency.agent_id == latest_subq.c.agent_id)
                        & (AgentEfficiency.created_at == latest_subq.c.max_created),
                    )
                    .limit(10_000)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

            for row in rows:
                stats = _AgentStats(
                    agent_type=row.agent_type or AgentType.CODER,
                    model_tier=row.model_tier or ModelTier.TIER_2,
                )
                stats.tasks_completed = row.tasks_completed
                stats.tasks_failed = row.tasks_failed
                stats.tokens_consumed = row.total_tokens_consumed
                stats.cost_usd = row.total_cost_usd
                stats.quality_sum = row.average_quality_score * max(row.tasks_completed, 1)
                scorer._agents[row.agent_id] = stats

            if rows:
                logger.info("efficiency scores restored from DB", agent_count=len(rows))
            else:
                logger.info("no persisted efficiency scores found — starting fresh")
        except Exception:
            logger.warning("failed to load persisted efficiency scores", exc_info=True)

        return scorer

    # ── Internals ────────────────────────────────────────────────────

    def _get_or_create(self, agent_id: AgentId) -> _AgentStats:
        key = str(agent_id)
        if key not in self._agents:
            self._agents[key] = _AgentStats()
        return self._agents[key]
