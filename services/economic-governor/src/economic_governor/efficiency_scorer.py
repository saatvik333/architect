"""Agent efficiency scoring.

Computes a per-agent efficiency metric defined as:

    efficiency = (tasks_completed * quality_score) / max(tokens_consumed, 1)

Scores are normalised to [0, 1] across the leaderboard and ranked.
"""

from __future__ import annotations

from architect_common.logging import get_logger
from architect_common.types import AgentId, utcnow
from economic_governor.models import AgentEfficiencyScore, EfficiencyLeaderboard

logger = get_logger(component="economic_governor.efficiency_scorer")


class _AgentStats:
    """Mutable accumulator for per-agent statistics."""

    __slots__ = ("cost_usd", "quality_sum", "tasks_completed", "tasks_failed", "tokens_consumed")

    def __init__(self) -> None:
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.quality_sum: float = 0.0
        self.tokens_consumed: int = 0
        self.cost_usd: float = 0.0


class EfficiencyScorer:
    """Accumulates per-agent task outcomes and produces ranked efficiency scores."""

    def __init__(self) -> None:
        self._agents: dict[str, _AgentStats] = {}
        self._cached_leaderboard: EfficiencyLeaderboard | None = None

    # ── Data ingestion ───────────────────────────────────────────────

    def record_task_completed(
        self,
        agent_id: AgentId,
        quality_score: float,
        tokens: int,
        cost_usd: float,
    ) -> None:
        """Record a successful task completion for an agent."""
        stats = self._get_or_create(agent_id)
        stats.tasks_completed += 1
        stats.quality_sum += quality_score
        stats.tokens_consumed += tokens
        stats.cost_usd += cost_usd
        self._cached_leaderboard = None

    def record_task_failed(self, agent_id: AgentId, tokens: int, cost_usd: float) -> None:
        """Record a failed task attempt for an agent."""
        stats = self._get_or_create(agent_id)
        stats.tasks_failed += 1
        stats.tokens_consumed += tokens
        stats.cost_usd += cost_usd
        self._cached_leaderboard = None

    # ── Scoring ──────────────────────────────────────────────────────

    def compute_scores(self) -> EfficiencyLeaderboard:
        """Compute and rank efficiency scores for all tracked agents.

        Returns:
            An :class:`EfficiencyLeaderboard` with entries sorted by efficiency
            (highest first).
        """
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

    def get_agent_score(self, agent_id: AgentId) -> AgentEfficiencyScore:
        """Return the efficiency score for a single agent.

        Uses the cached leaderboard when available to avoid recomputing
        on every single-agent lookup.

        If the agent has no recorded stats, returns a zeroed-out score.
        """
        leaderboard = self._cached_leaderboard or self.compute_scores()
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
        """Persist computed scores (stub — writes to log until DB wiring is added)."""
        logger.info(
            "persisting efficiency scores",
            agent_count=len(leaderboard.entries),
            computed_at=str(leaderboard.computed_at),
        )

    # ── Internals ────────────────────────────────────────────────────

    def _get_or_create(self, agent_id: AgentId) -> _AgentStats:
        key = str(agent_id)
        if key not in self._agents:
            self._agents[key] = _AgentStats()
        return self._agents[key]
