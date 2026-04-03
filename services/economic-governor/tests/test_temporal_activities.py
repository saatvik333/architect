"""Tests for Economic Governor Temporal activities."""

from __future__ import annotations

import pytest

from architect_common.enums import BudgetPhase, EnforcementLevel
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.temporal.activities import BudgetActivities


@pytest.fixture
def activities(
    budget_tracker: BudgetTracker,
    efficiency_scorer: EfficiencyScorer,
) -> BudgetActivities:
    """Return a BudgetActivities instance wired with test fixtures."""
    return BudgetActivities(budget_tracker, efficiency_scorer)


class TestBudgetActivities:
    """Unit tests for BudgetActivities Temporal activity methods."""

    async def test_get_budget_status_returns_correct_structure(
        self, activities: BudgetActivities
    ) -> None:
        """get_budget_status should return a dict with expected budget keys."""
        result = await activities.get_budget_status({})
        assert isinstance(result, dict)
        assert "consumed_tokens" in result
        assert "consumed_pct" in result
        assert "enforcement_level" in result
        assert "allocated_tokens" in result
        assert result["consumed_tokens"] == 0
        assert result["consumed_pct"] == 0.0

    async def test_record_consumption_valid_phase(self, activities: BudgetActivities) -> None:
        """record_consumption with a valid phase string should record correctly."""
        result = await activities.record_consumption(
            {
                "agent_id": "agent-test",
                "tokens": 5000,
                "cost_usd": 0.005,
                "phase": "testing",
            }
        )
        assert isinstance(result, dict)
        assert "enforcement_level" in result
        assert result["enforcement_level"] == EnforcementLevel.NONE.value

    async def test_record_consumption_invalid_phase_defaults(
        self, activities: BudgetActivities
    ) -> None:
        """record_consumption with invalid phase should default to IMPLEMENTATION."""
        result = await activities.record_consumption(
            {
                "agent_id": "agent-test",
                "tokens": 1000,
                "cost_usd": 0.001,
                "phase": "not_a_real_phase",
            }
        )
        assert isinstance(result, dict)
        assert "enforcement_level" in result

        # Verify the consumption was tracked under IMPLEMENTATION phase
        snapshot = await activities._tracker.get_snapshot()
        impl_phase = next(
            p for p in snapshot.phase_breakdown if p.phase == BudgetPhase.IMPLEMENTATION
        )
        assert impl_phase.consumed_tokens == 1000

    async def test_get_efficiency_leaderboard(self, activities: BudgetActivities) -> None:
        """compute_efficiency_scores should return a dict with entries list."""
        result = await activities.compute_efficiency_scores({})
        assert isinstance(result, dict)
        assert "entries" in result
        assert isinstance(result["entries"], list)

    async def test_check_budget_for_task_allowed(self, activities: BudgetActivities) -> None:
        """check_budget_for_task should allow a task within budget."""
        result = await activities.check_budget_for_task(
            {
                "estimated_tokens": 100,
            }
        )
        assert isinstance(result, dict)
        assert result["allowed"] is True
        assert "remaining_tokens" in result

    async def test_check_budget_for_task_denied_at_halt(
        self, activities: BudgetActivities, config: EconomicGovernorConfig
    ) -> None:
        """check_budget_for_task should deny when budget is at HALT level."""
        total = config.architect.budget.total_tokens
        await activities._tracker.record_consumption(
            agent_id="agent-exhaust", tokens=total, cost_usd=1.0
        )
        result = await activities.check_budget_for_task(
            {
                "estimated_tokens": 1,
            }
        )
        assert result["allowed"] is False

    async def test_enforce_budget_action_taken(self, activities: BudgetActivities) -> None:
        """enforce_budget should report action_taken=True for non-none levels."""
        result = await activities.enforce_budget({"level": "alert"})
        assert result["action_taken"] is True
        assert result["level"] == "alert"

    async def test_enforce_budget_no_action(self, activities: BudgetActivities) -> None:
        """enforce_budget should report action_taken=False for level 'none'."""
        result = await activities.enforce_budget({"level": "none"})
        assert result["action_taken"] is False
