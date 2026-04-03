"""Tests for the EfficiencyScorer."""

from __future__ import annotations

from architect_common.types import AgentId
from economic_governor.efficiency_scorer import EfficiencyScorer


class TestEfficiencyScorer:
    """Unit tests for efficiency scoring logic."""

    async def test_empty_leaderboard(self, efficiency_scorer: EfficiencyScorer) -> None:
        """Leaderboard should be empty with no recorded tasks."""
        board = await efficiency_scorer.compute_scores()
        assert len(board.entries) == 0

    async def test_single_agent_score(self, efficiency_scorer: EfficiencyScorer) -> None:
        """A single agent should have rank 1 and normalised score of 1.0."""
        agent = AgentId("agent-solo")
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=0.9, tokens=10000, cost_usd=0.01
        )
        board = await efficiency_scorer.compute_scores()

        assert len(board.entries) == 1
        entry = board.entries[0]
        assert entry.agent_id == agent
        assert entry.rank == 1
        assert entry.efficiency_score == 1.0  # Normalised max
        assert entry.tasks_completed == 1
        assert entry.quality_score == 0.9

    async def test_multiple_agents_ranked(self, efficiency_scorer: EfficiencyScorer) -> None:
        """Agents should be ranked by efficiency (higher is better)."""
        # Agent A: high quality, low tokens.
        agent_a = AgentId("agent-efficient")
        await efficiency_scorer.record_task_completed(
            agent_id=agent_a, quality_score=1.0, tokens=1000, cost_usd=0.001
        )

        # Agent B: lower quality, higher tokens.
        agent_b = AgentId("agent-expensive")
        await efficiency_scorer.record_task_completed(
            agent_id=agent_b, quality_score=0.5, tokens=10000, cost_usd=0.01
        )

        board = await efficiency_scorer.compute_scores()
        assert len(board.entries) == 2
        assert board.entries[0].agent_id == agent_a
        assert board.entries[0].rank == 1
        assert board.entries[1].agent_id == agent_b
        assert board.entries[1].rank == 2
        # Agent A should have higher efficiency score.
        assert board.entries[0].efficiency_score > board.entries[1].efficiency_score

    async def test_failed_tasks_tracked(self, efficiency_scorer: EfficiencyScorer) -> None:
        """Failed tasks should be counted and reduce efficiency."""
        agent = AgentId("agent-mixed")
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=0.8, tokens=5000, cost_usd=0.005
        )
        await efficiency_scorer.record_task_failed(agent_id=agent, tokens=3000, cost_usd=0.003)

        board = await efficiency_scorer.compute_scores()
        entry = board.entries[0]
        assert entry.tasks_completed == 1
        assert entry.tasks_failed == 1
        assert entry.tokens_consumed == 8000

    async def test_get_agent_score_existing(self, efficiency_scorer: EfficiencyScorer) -> None:
        """get_agent_score should return the correct score for a tracked agent."""
        agent = AgentId("agent-lookup")
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=0.75, tokens=2000, cost_usd=0.002
        )

        score = await efficiency_scorer.get_agent_score(agent)
        assert score.agent_id == agent
        assert score.tasks_completed == 1

    async def test_get_agent_score_unknown(self, efficiency_scorer: EfficiencyScorer) -> None:
        """get_agent_score should return a default for unknown agents."""
        score = await efficiency_scorer.get_agent_score(AgentId("agent-unknown"))
        assert score.efficiency_score == 0.0
        assert score.tasks_completed == 0

    async def test_efficiency_formula(self, efficiency_scorer: EfficiencyScorer) -> None:
        """Verify the efficiency formula: (completed * quality) / tokens."""
        agent = AgentId("agent-formula")
        # 2 tasks completed with quality 1.0, 4000 tokens total.
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=1.0, tokens=2000, cost_usd=0.002
        )
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=1.0, tokens=2000, cost_usd=0.002
        )

        board = await efficiency_scorer.compute_scores()
        entry = board.entries[0]
        # raw_eff = (2 * 1.0) / 4000 = 0.0005
        # Normalised to 1.0 since it's the only agent.
        assert entry.efficiency_score == 1.0
        assert entry.tasks_completed == 2
        assert entry.tokens_consumed == 4000

    async def test_zero_quality_yields_zero_efficiency(
        self, efficiency_scorer: EfficiencyScorer
    ) -> None:
        """An agent with zero quality should have zero efficiency."""
        agent = AgentId("agent-zero")
        await efficiency_scorer.record_task_completed(
            agent_id=agent, quality_score=0.0, tokens=5000, cost_usd=0.005
        )

        board = await efficiency_scorer.compute_scores()
        entry = board.entries[0]
        # raw_eff = (1 * 0.0) / 5000 = 0.0 → normalised stays 0.0
        assert entry.efficiency_score == 0.0
