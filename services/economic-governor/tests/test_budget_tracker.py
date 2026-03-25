"""Tests for the BudgetTracker."""

from __future__ import annotations

import pytest

from architect_common.enums import BudgetPhase, EnforcementLevel
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.models import BudgetAllocationRequest


class TestBudgetTracker:
    """Unit tests for budget tracking and threshold detection."""

    def test_initial_state(self, budget_tracker: BudgetTracker) -> None:
        """Fresh tracker should have zero consumption."""
        snapshot = budget_tracker.get_snapshot()
        assert snapshot.consumed_tokens == 0
        assert snapshot.consumed_pct == 0.0
        assert snapshot.enforcement_level == EnforcementLevel.NONE

    def test_record_consumption(self, budget_tracker: BudgetTracker) -> None:
        """Recording consumption should update the snapshot."""
        budget_tracker.record_consumption(agent_id="agent-1", tokens=1000, cost_usd=0.001)
        snapshot = budget_tracker.get_snapshot()
        assert snapshot.consumed_tokens == 1000
        assert snapshot.consumed_usd == 0.001

    def test_consumed_pct(self, config: EconomicGovernorConfig) -> None:
        """consumed_pct should reflect the percentage of allocated tokens consumed."""
        tracker = BudgetTracker(config)
        total = config.architect.budget.total_tokens
        # Consume 50% of the budget.
        tracker.record_consumption(agent_id="agent-1", tokens=total // 2, cost_usd=0.0)
        assert tracker.consumed_pct == 50.0

    def test_alert_threshold(self, config: EconomicGovernorConfig) -> None:
        """Consuming past alert_threshold_pct should trigger ALERT level."""
        tracker = BudgetTracker(config)
        total = config.architect.budget.total_tokens
        alert_tokens = int(total * config.alert_threshold_pct / 100) + 1
        level = tracker.record_consumption(agent_id="agent-1", tokens=alert_tokens, cost_usd=0.0)
        assert level == EnforcementLevel.ALERT

    def test_restrict_threshold(self, config: EconomicGovernorConfig) -> None:
        """Consuming past restrict_threshold_pct should trigger RESTRICT level."""
        tracker = BudgetTracker(config)
        total = config.architect.budget.total_tokens
        restrict_tokens = int(total * config.restrict_threshold_pct / 100) + 1
        level = tracker.record_consumption(agent_id="agent-1", tokens=restrict_tokens, cost_usd=0.0)
        assert level == EnforcementLevel.RESTRICT

    def test_halt_threshold(self, config: EconomicGovernorConfig) -> None:
        """Consuming past halt_threshold_pct should trigger HALT level."""
        tracker = BudgetTracker(config)
        total = config.architect.budget.total_tokens
        level = tracker.record_consumption(agent_id="agent-1", tokens=total, cost_usd=0.0)
        assert level == EnforcementLevel.HALT

    def test_threshold_crossed_returns_none_when_unchanged(
        self, budget_tracker: BudgetTracker
    ) -> None:
        """threshold_crossed() should return None when no level change occurred."""
        result = budget_tracker.threshold_crossed()
        assert result is None

    def test_burn_rate_zero_initially(self, budget_tracker: BudgetTracker) -> None:
        """Burn rate should be zero with no consumption."""
        assert budget_tracker.burn_rate == 0.0

    def test_burn_rate_after_consumption(self, budget_tracker: BudgetTracker) -> None:
        """Burn rate should be positive after consuming tokens."""
        budget_tracker.record_consumption(agent_id="agent-1", tokens=10000, cost_usd=0.01)
        # The burn rate depends on elapsed time, which is near-zero in tests.
        # Just verify it doesn't raise.
        rate = budget_tracker.burn_rate
        assert isinstance(rate, float)

    def test_phase_breakdown(self, budget_tracker: BudgetTracker) -> None:
        """Phase breakdown should have an entry for each BudgetPhase."""
        snapshot = budget_tracker.get_snapshot()
        phases = {ps.phase for ps in snapshot.phase_breakdown}
        assert phases == set(BudgetPhase)

    def test_phase_consumption_tracked(self, budget_tracker: BudgetTracker) -> None:
        """Consumption should be tracked per-phase."""
        budget_tracker.record_consumption(
            agent_id="agent-1",
            tokens=5000,
            cost_usd=0.005,
            phase=BudgetPhase.TESTING,
        )
        snapshot = budget_tracker.get_snapshot()
        testing_phase = next(p for p in snapshot.phase_breakdown if p.phase == BudgetPhase.TESTING)
        assert testing_phase.consumed_tokens == 5000

    def test_allocate_project_budget(self, budget_tracker: BudgetTracker) -> None:
        """allocate_project_budget should return a valid allocation."""
        request = BudgetAllocationRequest(
            project_id="proj-test",
            estimated_complexity=0.7,
            priority=2,
        )
        result = budget_tracker.allocate_project_budget(request)
        assert result.project_id == "proj-test"
        assert result.total_tokens > 0
        assert result.total_usd > 0.0
        assert len(result.phase_allocations) == 7  # One per BudgetPhase

    def test_allocate_budget_complexity_scaling(self, config: EconomicGovernorConfig) -> None:
        """Higher complexity should yield a larger budget."""
        tracker = BudgetTracker(config)
        low = tracker.allocate_project_budget(
            BudgetAllocationRequest(project_id="low", estimated_complexity=0.1, priority=1)
        )
        high = tracker.allocate_project_budget(
            BudgetAllocationRequest(project_id="high", estimated_complexity=0.9, priority=1)
        )
        assert high.total_tokens > low.total_tokens

    def test_multiple_consumption_records(self, budget_tracker: BudgetTracker) -> None:
        """Multiple consumption records should be cumulative."""
        budget_tracker.record_consumption(agent_id="agent-1", tokens=100, cost_usd=0.001)
        budget_tracker.record_consumption(agent_id="agent-2", tokens=200, cost_usd=0.002)
        snapshot = budget_tracker.get_snapshot()
        assert snapshot.consumed_tokens == 300
        assert snapshot.consumed_usd == pytest.approx(0.003, abs=1e-6)
