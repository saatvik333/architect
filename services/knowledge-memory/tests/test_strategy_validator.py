"""Tests for the strategy validator module."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from knowledge_memory.models import MetaStrategy
from knowledge_memory.strategy_validator import (
    assign_ab_group,
    evaluate_strategy,
    get_success_rate,
    record_outcome,
    run_validation_cycle,
)


class TestAssignAbGroup:
    def test_deterministic(self) -> None:
        group1 = assign_ab_group("task-abc", "test-1")
        group2 = assign_ab_group("task-abc", "test-1")
        assert group1 == group2

    def test_different_tasks_may_differ(self) -> None:
        groups = {assign_ab_group(f"task-{i}", "test-1") for i in range(100)}
        assert len(groups) == 2  # Both control and experiment should appear

    def test_valid_groups(self) -> None:
        group = assign_ab_group("task-xyz", "test-1")
        assert group in ("control", "experiment")


class TestRecordOutcome:
    def test_success(self) -> None:
        strategy = MetaStrategy(name="test", description="test strategy")
        updated = record_outcome(strategy, success=True)
        assert updated.tasks_applied == 1
        assert updated.tasks_succeeded == 1
        assert updated.tasks_failed == 0

    def test_failure(self) -> None:
        strategy = MetaStrategy(name="test", description="test strategy")
        updated = record_outcome(strategy, success=False)
        assert updated.tasks_applied == 1
        assert updated.tasks_succeeded == 0
        assert updated.tasks_failed == 1

    def test_accumulates(self) -> None:
        strategy = MetaStrategy(
            name="test",
            description="test",
            tasks_applied=10,
            tasks_succeeded=7,
            tasks_failed=3,
        )
        updated = record_outcome(strategy, success=True)
        assert updated.tasks_applied == 11
        assert updated.tasks_succeeded == 8
        assert updated.tasks_failed == 3

    def test_immutable(self) -> None:
        strategy = MetaStrategy(name="test", description="test")
        updated = record_outcome(strategy, success=True)
        assert strategy.tasks_applied == 0  # Original unchanged
        assert updated.tasks_applied == 1


class TestEvaluateStrategy:
    def test_insufficient_data(self) -> None:
        strategy = MetaStrategy(name="test", description="test", tasks_applied=5, tasks_succeeded=4)
        assert evaluate_strategy(strategy, min_samples=30) == "insufficient_data"

    def test_validated(self) -> None:
        # 90% success rate vs 50% baseline with 100 samples
        strategy = MetaStrategy(
            name="test",
            description="test",
            tasks_applied=100,
            tasks_succeeded=90,
            tasks_failed=10,
        )
        assert evaluate_strategy(strategy, baseline_success_rate=0.5) == "validated"

    def test_rejected(self) -> None:
        # 10% success rate vs 50% baseline with 100 samples
        strategy = MetaStrategy(
            name="test",
            description="test",
            tasks_applied=100,
            tasks_succeeded=10,
            tasks_failed=90,
        )
        assert evaluate_strategy(strategy, baseline_success_rate=0.5) == "rejected"

    def test_inconclusive(self) -> None:
        # 52% success rate vs 50% baseline — not significant
        strategy = MetaStrategy(
            name="test",
            description="test",
            tasks_applied=50,
            tasks_succeeded=26,
            tasks_failed=24,
        )
        assert evaluate_strategy(strategy, baseline_success_rate=0.5) == "inconclusive"


class TestGetSuccessRate:
    def test_zero_tasks(self) -> None:
        strategy = MetaStrategy(name="test", description="test")
        assert get_success_rate(strategy) == 0.0

    def test_with_data(self) -> None:
        strategy = MetaStrategy(
            name="test",
            description="test",
            tasks_applied=10,
            tasks_succeeded=7,
        )
        assert get_success_rate(strategy) == pytest.approx(0.7)


class TestRunValidationCycle:
    @pytest.mark.asyncio
    async def test_categorizes_strategies(self) -> None:
        strategies = [
            MetaStrategy(
                name="good",
                description="good strategy",
                tasks_applied=100,
                tasks_succeeded=90,
                tasks_failed=10,
            ),
            MetaStrategy(
                name="bad",
                description="bad strategy",
                tasks_applied=100,
                tasks_succeeded=10,
                tasks_failed=90,
            ),
            MetaStrategy(
                name="new",
                description="new strategy",
                tasks_applied=5,
                tasks_succeeded=3,
                tasks_failed=2,
            ),
        ]

        results = await run_validation_cycle(strategies, baseline_success_rate=0.5)
        assert len(results["validated"]) == 1
        assert len(results["rejected"]) == 1
        assert len(results["insufficient_data"]) == 1

    @pytest.mark.asyncio
    async def test_skips_already_finalized(self) -> None:
        strategies = [
            MetaStrategy(
                name="already_done",
                description="already validated",
                validation_status="validated",
                tasks_applied=100,
                tasks_succeeded=90,
            ),
        ]
        results = await run_validation_cycle(strategies)
        assert all(len(v) == 0 for v in results.values())
