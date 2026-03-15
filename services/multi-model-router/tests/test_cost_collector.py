"""Tests for Multi-Model Router cost tracking."""

from __future__ import annotations

import pytest

from architect_common.enums import ModelTier
from architect_common.types import TaskId
from multi_model_router.cost_collector import CostCollector
from multi_model_router.models import (
    ComplexityScore,
    CostSavingsReport,
    CostSummary,
    RoutingDecision,
    RoutingStats,
    TierCost,
)


def _make_decision(
    tier: ModelTier,
    task_id: str = "task-test000001",
) -> RoutingDecision:
    """Helper to build a RoutingDecision for the given tier."""
    model_map = {
        ModelTier.TIER_1: "claude-opus-4-20250514",
        ModelTier.TIER_2: "claude-sonnet-4-20250514",
        ModelTier.TIER_3: "claude-haiku-3-20250305",
    }
    return RoutingDecision(
        task_id=TaskId(task_id),
        selected_tier=tier,
        model_id=model_map[tier],
        complexity=ComplexityScore(score=0.5, factors={}, recommended_tier=tier),
    )


class TestCostCollectorRecording:
    """Tests for recording routing events."""

    def test_record_single_routing_returns_cost(self) -> None:
        """record_routing should return the computed cost in USD."""
        collector = CostCollector()
        decision = _make_decision(ModelTier.TIER_3)
        cost = collector.record_routing(decision, input_tokens=1000, output_tokens=500)
        # Haiku: 0.25/1M input, 1.25/1M output
        expected = (1000 * 0.25 / 1_000_000) + (500 * 1.25 / 1_000_000)
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_record_tier1_routing(self) -> None:
        """Tier 1 (Opus) pricing should be applied correctly."""
        collector = CostCollector()
        decision = _make_decision(ModelTier.TIER_1)
        cost = collector.record_routing(decision, input_tokens=1000, output_tokens=500)
        expected = (1000 * 15.0 / 1_000_000) + (500 * 75.0 / 1_000_000)
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_record_tier2_routing(self) -> None:
        """Tier 2 (Sonnet) pricing should be applied correctly."""
        collector = CostCollector()
        decision = _make_decision(ModelTier.TIER_2)
        cost = collector.record_routing(decision, input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.0 / 1_000_000) + (500 * 15.0 / 1_000_000)
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_record_zero_tokens(self) -> None:
        """Recording with zero tokens should return zero cost."""
        collector = CostCollector()
        decision = _make_decision(ModelTier.TIER_2)
        cost = collector.record_routing(decision, input_tokens=0, output_tokens=0)
        assert cost == 0.0


class TestCostSummary:
    """Tests for cost summary aggregation."""

    def test_empty_collector_returns_zero_summary(self) -> None:
        """A fresh collector should return an empty summary."""
        collector = CostCollector()
        summary = collector.get_cost_summary()
        assert isinstance(summary, CostSummary)
        assert summary.total_cost_usd == 0.0
        assert summary.total_requests == 0
        assert summary.cost_by_tier == []

    def test_summary_aggregates_multiple_tiers(self) -> None:
        """Summary should correctly aggregate costs across different tiers."""
        collector = CostCollector()

        # Record requests at different tiers
        d1 = _make_decision(ModelTier.TIER_1, "task-t1-000001")
        d2 = _make_decision(ModelTier.TIER_2, "task-t2-000001")
        d3 = _make_decision(ModelTier.TIER_3, "task-t3-000001")

        cost1 = collector.record_routing(d1, input_tokens=1000, output_tokens=500)
        cost2 = collector.record_routing(d2, input_tokens=2000, output_tokens=1000)
        cost3 = collector.record_routing(d3, input_tokens=5000, output_tokens=2000)

        summary = collector.get_cost_summary()
        assert summary.total_requests == 3
        assert summary.total_cost_usd == pytest.approx(cost1 + cost2 + cost3, rel=1e-6)
        assert len(summary.cost_by_tier) == 3

        # Check tier ordering (TIER_1, TIER_2, TIER_3)
        tier_names = [tc.tier for tc in summary.cost_by_tier]
        assert tier_names == [ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3]

    def test_summary_token_counts(self) -> None:
        """Summary should track input and output tokens per tier."""
        collector = CostCollector()
        d = _make_decision(ModelTier.TIER_2)
        collector.record_routing(d, input_tokens=1000, output_tokens=500)
        collector.record_routing(d, input_tokens=2000, output_tokens=1500)

        summary = collector.get_cost_summary()
        assert len(summary.cost_by_tier) == 1
        tier_cost: TierCost = summary.cost_by_tier[0]
        assert tier_cost.input_tokens == 3000
        assert tier_cost.output_tokens == 2000
        assert tier_cost.total_tokens == 5000


class TestCostSavingsReport:
    """Tests for savings calculation (actual vs all-Tier-1)."""

    def test_empty_collector_returns_zero_savings(self) -> None:
        """A fresh collector should report zero savings."""
        collector = CostCollector()
        report = collector.get_cost_savings()
        assert isinstance(report, CostSavingsReport)
        assert report.actual_cost_usd == 0.0
        assert report.hypothetical_all_tier1_cost_usd == 0.0
        assert report.savings_usd == 0.0
        assert report.savings_percentage == 0.0

    def test_tier3_saves_vs_tier1(self) -> None:
        """Using Tier 3 should show savings compared to Tier 1."""
        collector = CostCollector()
        d = _make_decision(ModelTier.TIER_3)
        collector.record_routing(d, input_tokens=10_000, output_tokens=5_000)

        report = collector.get_cost_savings()
        # Haiku actual cost
        actual = (10_000 * 0.25 / 1_000_000) + (5_000 * 1.25 / 1_000_000)
        # Opus hypothetical cost
        hypothetical = (10_000 * 15.0 / 1_000_000) + (5_000 * 75.0 / 1_000_000)

        assert report.actual_cost_usd == pytest.approx(actual, rel=1e-6)
        assert report.hypothetical_all_tier1_cost_usd == pytest.approx(hypothetical, rel=1e-6)
        assert report.savings_usd == pytest.approx(hypothetical - actual, rel=1e-6)
        assert report.savings_percentage > 95.0  # Haiku is much cheaper than Opus

    def test_tier1_shows_no_savings(self) -> None:
        """Using Tier 1 should show zero savings."""
        collector = CostCollector()
        d = _make_decision(ModelTier.TIER_1)
        collector.record_routing(d, input_tokens=1000, output_tokens=500)

        report = collector.get_cost_savings()
        assert report.savings_usd == pytest.approx(0.0, abs=1e-10)
        assert report.savings_percentage == pytest.approx(0.0, abs=0.01)

    def test_mixed_tiers_savings(self) -> None:
        """A mix of tiers should show intermediate savings."""
        collector = CostCollector()
        d1 = _make_decision(ModelTier.TIER_1, "task-mix000001")
        d3 = _make_decision(ModelTier.TIER_3, "task-mix000002")
        collector.record_routing(d1, input_tokens=1000, output_tokens=500)
        collector.record_routing(d3, input_tokens=1000, output_tokens=500)

        report = collector.get_cost_savings()
        # Savings come only from the Tier 3 request
        assert report.savings_usd > 0
        assert 0 < report.savings_percentage < 100


class TestRoutingStats:
    """Tests for the get_stats() method including cost fields."""

    def test_stats_include_cost_fields(self) -> None:
        """Stats should include total_cost_usd and estimated_savings_usd."""
        collector = CostCollector()
        d = _make_decision(ModelTier.TIER_3)
        collector.record_routing(d, input_tokens=10_000, output_tokens=5_000)

        stats = collector.get_stats()
        assert isinstance(stats, RoutingStats)
        assert stats.total_requests == 1
        assert stats.total_cost_usd > 0
        assert stats.estimated_savings_usd > 0

    def test_stats_tier_distribution(self) -> None:
        """Stats tier_distribution should reflect actual routing counts."""
        collector = CostCollector()
        for _ in range(3):
            d = _make_decision(ModelTier.TIER_2)
            collector.record_routing(d, input_tokens=100, output_tokens=50)
        for _ in range(2):
            d = _make_decision(ModelTier.TIER_3)
            collector.record_routing(d, input_tokens=100, output_tokens=50)

        stats = collector.get_stats()
        assert stats.total_requests == 5
        assert stats.tier_distribution["tier_2"] == 3
        assert stats.tier_distribution["tier_3"] == 2

    def test_stats_average_complexity(self) -> None:
        """Stats should compute correct average complexity."""
        collector = CostCollector()
        # Two decisions with complexity 0.3 and 0.7 => average 0.5
        d1 = RoutingDecision(
            task_id=TaskId("task-cplx00001"),
            selected_tier=ModelTier.TIER_2,
            model_id="claude-sonnet-4-20250514",
            complexity=ComplexityScore(score=0.3, factors={}, recommended_tier=ModelTier.TIER_2),
        )
        d2 = RoutingDecision(
            task_id=TaskId("task-cplx00002"),
            selected_tier=ModelTier.TIER_1,
            model_id="claude-opus-4-20250514",
            complexity=ComplexityScore(score=0.7, factors={}, recommended_tier=ModelTier.TIER_1),
        )
        collector.record_routing(d1, input_tokens=100, output_tokens=50)
        collector.record_routing(d2, input_tokens=100, output_tokens=50)

        stats = collector.get_stats()
        assert stats.average_complexity == pytest.approx(0.5, rel=1e-4)

    def test_stats_escalation_count(self) -> None:
        """Stats should track escalation count."""
        collector = CostCollector()
        collector.record_escalation()
        collector.record_escalation()
        stats = collector.get_stats()
        assert stats.escalation_count == 2
