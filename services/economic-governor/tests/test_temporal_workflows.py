"""Tests for Economic Governor Temporal workflows and activities.

Tests the activity implementations by mocking the underlying BudgetTracker
and EfficiencyScorer, and tests workflow dataclass parameter handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.enums import BudgetPhase, EnforcementLevel

# ── Helpers ──────────────────────────────────────────────────────


def _mock_snapshot(
    *,
    allocated_tokens: int = 100_000,
    consumed_tokens: int = 50_000,
    consumed_pct: float = 50.0,
    enforcement_level: str = EnforcementLevel.NONE,
) -> MagicMock:
    """Create a mock BudgetSnapshot with model_dump support."""
    snapshot = MagicMock()
    snapshot.allocated_tokens = allocated_tokens
    snapshot.consumed_tokens = consumed_tokens
    snapshot.consumed_pct = consumed_pct
    snapshot.enforcement_level = enforcement_level
    snapshot.model_dump.return_value = {
        "allocated_tokens": allocated_tokens,
        "consumed_tokens": consumed_tokens,
        "consumed_pct": consumed_pct,
        "enforcement_level": enforcement_level,
    }
    return snapshot


def _make_activities(
    *,
    tracker: AsyncMock | None = None,
    scorer: AsyncMock | None = None,
) -> BudgetActivities:  # noqa: F821
    """Create a BudgetActivities instance with mocked dependencies."""
    from economic_governor.temporal.activities import BudgetActivities

    return BudgetActivities(
        budget_tracker=tracker or AsyncMock(),
        efficiency_scorer=scorer or AsyncMock(),
    )


# ── BudgetActivities Tests ──────────────────────────────────────


class TestGetBudgetStatus:
    """Tests for the get_budget_status activity."""

    @pytest.mark.asyncio
    async def test_returns_serialised_snapshot(self) -> None:
        tracker = AsyncMock()
        snapshot = _mock_snapshot()
        tracker.get_snapshot.return_value = snapshot

        activities = _make_activities(tracker=tracker)
        result = await activities.get_budget_status({})

        tracker.get_snapshot.assert_awaited_once()
        snapshot.model_dump.assert_called_once_with(mode="json")
        assert result == snapshot.model_dump.return_value

    @pytest.mark.asyncio
    async def test_returns_dict(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot()

        activities = _make_activities(tracker=tracker)
        result = await activities.get_budget_status({})

        assert isinstance(result, dict)
        assert "allocated_tokens" in result


class TestCheckBudgetForTask:
    """Tests for the check_budget_for_task activity."""

    @pytest.mark.asyncio
    async def test_allowed_when_sufficient_budget(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot(
            allocated_tokens=100_000,
            consumed_tokens=10_000,
            enforcement_level=EnforcementLevel.NONE,
        )

        activities = _make_activities(tracker=tracker)
        result = await activities.check_budget_for_task({"estimated_tokens": 5000})

        assert result["allowed"] is True
        assert result["remaining_tokens"] == 90_000

    @pytest.mark.asyncio
    async def test_denied_when_insufficient_budget(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot(
            allocated_tokens=100_000,
            consumed_tokens=99_000,
            enforcement_level=EnforcementLevel.NONE,
        )

        activities = _make_activities(tracker=tracker)
        result = await activities.check_budget_for_task({"estimated_tokens": 5000})

        assert result["allowed"] is False
        assert result["remaining_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_denied_when_halted(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot(
            allocated_tokens=100_000,
            consumed_tokens=0,
            enforcement_level=EnforcementLevel.HALT,
        )

        activities = _make_activities(tracker=tracker)
        result = await activities.check_budget_for_task({"estimated_tokens": 100})

        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_returns_consumed_pct(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot(consumed_pct=75.0)

        activities = _make_activities(tracker=tracker)
        result = await activities.check_budget_for_task({"estimated_tokens": 0})

        assert result["consumed_pct"] == 75.0

    @pytest.mark.asyncio
    async def test_defaults_estimated_tokens_to_zero(self) -> None:
        tracker = AsyncMock()
        tracker.get_snapshot.return_value = _mock_snapshot(
            allocated_tokens=100_000,
            consumed_tokens=50_000,
            enforcement_level=EnforcementLevel.NONE,
        )

        activities = _make_activities(tracker=tracker)
        result = await activities.check_budget_for_task({})

        assert result["allowed"] is True


class TestRecordConsumption:
    """Tests for the record_consumption activity."""

    @pytest.mark.asyncio
    async def test_delegates_to_tracker(self) -> None:
        tracker = AsyncMock()
        tracker.record_consumption.return_value = EnforcementLevel.NONE

        activities = _make_activities(tracker=tracker)
        result = await activities.record_consumption(
            {"agent_id": "agent-1", "tokens": 1000, "cost_usd": 0.01}
        )

        tracker.record_consumption.assert_awaited_once_with(
            agent_id="agent-1",
            tokens=1000,
            cost_usd=0.01,
            phase=BudgetPhase.IMPLEMENTATION,
        )
        assert result["enforcement_level"] == "none"

    @pytest.mark.asyncio
    async def test_returns_enforcement_level(self) -> None:
        tracker = AsyncMock()
        tracker.record_consumption.return_value = EnforcementLevel.ALERT

        activities = _make_activities(tracker=tracker)
        result = await activities.record_consumption(
            {"agent_id": "agent-1", "tokens": 50000, "cost_usd": 0.50}
        )

        assert result["enforcement_level"] == "alert"

    @pytest.mark.asyncio
    async def test_parses_phase_parameter(self) -> None:
        tracker = AsyncMock()
        tracker.record_consumption.return_value = EnforcementLevel.NONE

        activities = _make_activities(tracker=tracker)
        await activities.record_consumption(
            {
                "agent_id": "agent-1",
                "tokens": 500,
                "cost_usd": 0.005,
                "phase": "testing",
            }
        )

        tracker.record_consumption.assert_awaited_once_with(
            agent_id="agent-1",
            tokens=500,
            cost_usd=0.005,
            phase=BudgetPhase.TESTING,
        )

    @pytest.mark.asyncio
    async def test_invalid_phase_defaults_to_implementation(self) -> None:
        tracker = AsyncMock()
        tracker.record_consumption.return_value = EnforcementLevel.NONE

        activities = _make_activities(tracker=tracker)
        await activities.record_consumption(
            {
                "agent_id": "agent-1",
                "tokens": 500,
                "cost_usd": 0.005,
                "phase": "nonexistent_phase",
            }
        )

        tracker.record_consumption.assert_awaited_once_with(
            agent_id="agent-1",
            tokens=500,
            cost_usd=0.005,
            phase=BudgetPhase.IMPLEMENTATION,
        )

    @pytest.mark.asyncio
    async def test_defaults_for_missing_fields(self) -> None:
        tracker = AsyncMock()
        tracker.record_consumption.return_value = EnforcementLevel.NONE

        activities = _make_activities(tracker=tracker)
        await activities.record_consumption({})

        tracker.record_consumption.assert_awaited_once_with(
            agent_id="unknown",
            tokens=0,
            cost_usd=0.0,
            phase=BudgetPhase.IMPLEMENTATION,
        )


class TestComputeEfficiencyScores:
    """Tests for the compute_efficiency_scores activity."""

    @pytest.mark.asyncio
    async def test_delegates_to_scorer(self) -> None:
        scorer = AsyncMock()
        leaderboard = MagicMock()
        leaderboard.model_dump.return_value = {"entries": [], "computed_at": "2026-01-01T00:00:00Z"}
        scorer.compute_scores.return_value = leaderboard

        activities = _make_activities(scorer=scorer)
        result = await activities.compute_efficiency_scores({})

        scorer.compute_scores.assert_awaited_once()
        leaderboard.model_dump.assert_called_once_with(mode="json")
        assert result == leaderboard.model_dump.return_value

    @pytest.mark.asyncio
    async def test_returns_dict(self) -> None:
        scorer = AsyncMock()
        leaderboard = MagicMock()
        leaderboard.model_dump.return_value = {"entries": []}
        scorer.compute_scores.return_value = leaderboard

        activities = _make_activities(scorer=scorer)
        result = await activities.compute_efficiency_scores({})

        assert isinstance(result, dict)


class TestEnforceBudget:
    """Tests for the enforce_budget activity."""

    @pytest.mark.asyncio
    async def test_action_taken_when_not_none(self) -> None:
        activities = _make_activities()
        result = await activities.enforce_budget({"level": "alert"})

        assert result["action_taken"] is True
        assert result["level"] == "alert"

    @pytest.mark.asyncio
    async def test_no_action_when_none(self) -> None:
        activities = _make_activities()
        result = await activities.enforce_budget({"level": "none"})

        assert result["action_taken"] is False
        assert result["level"] == "none"

    @pytest.mark.asyncio
    async def test_defaults_to_none_level(self) -> None:
        activities = _make_activities()
        result = await activities.enforce_budget({})

        assert result["action_taken"] is False
        assert result["level"] == "none"

    @pytest.mark.asyncio
    async def test_halt_level(self) -> None:
        activities = _make_activities()
        result = await activities.enforce_budget({"level": "halt"})

        assert result["action_taken"] is True
        assert result["level"] == "halt"


# ── Workflow Dataclass Tests ────────────────────────────────────


class TestBudgetMonitoringParams:
    """Tests for BudgetMonitoringParams dataclass."""

    def test_defaults(self) -> None:
        from economic_governor.temporal.workflows import BudgetMonitoringParams

        params = BudgetMonitoringParams()
        assert params.poll_interval_seconds == 60
        assert params.efficiency_interval_seconds == 300
        assert params.max_iterations == 1000

    def test_custom_values(self) -> None:
        from economic_governor.temporal.workflows import BudgetMonitoringParams

        params = BudgetMonitoringParams(
            poll_interval_seconds=30,
            efficiency_interval_seconds=120,
            max_iterations=500,
        )
        assert params.poll_interval_seconds == 30
        assert params.efficiency_interval_seconds == 120
        assert params.max_iterations == 500


class TestBudgetMonitoringResult:
    """Tests for BudgetMonitoringResult dataclass."""

    def test_defaults(self) -> None:
        from economic_governor.temporal.workflows import BudgetMonitoringResult

        result = BudgetMonitoringResult()
        assert result.iterations_completed == 0
        assert result.final_level == "none"
        assert result.completed is False

    def test_custom_values(self) -> None:
        from economic_governor.temporal.workflows import BudgetMonitoringResult

        result = BudgetMonitoringResult(
            iterations_completed=100,
            final_level="halt",
            completed=True,
        )
        assert result.iterations_completed == 100
        assert result.final_level == "halt"
        assert result.completed is True


class TestBudgetAllocationParams:
    """Tests for BudgetAllocationParams dataclass."""

    def test_defaults(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationParams

        params = BudgetAllocationParams()
        assert params.task_id == ""
        assert params.estimated_tokens == 0
        assert params.agent_id == "unknown"
        assert params.cost_usd == 0.0

    def test_custom_values(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationParams

        params = BudgetAllocationParams(
            task_id="task-123",
            estimated_tokens=5000,
            agent_id="agent-abc",
            cost_usd=0.05,
        )
        assert params.task_id == "task-123"
        assert params.estimated_tokens == 5000
        assert params.agent_id == "agent-abc"
        assert params.cost_usd == 0.05

    def test_from_dict_filters_unknown_keys(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationParams

        data = {
            "task_id": "task-1",
            "estimated_tokens": 1000,
            "unknown_key": "should_be_ignored",
        }
        params = BudgetAllocationParams(
            **{k: v for k, v in data.items() if k in BudgetAllocationParams.__dataclass_fields__}
        )
        assert params.task_id == "task-1"
        assert params.estimated_tokens == 1000
        assert params.agent_id == "unknown"  # default


class TestBudgetAllocationResult:
    """Tests for BudgetAllocationResult dataclass."""

    def test_defaults(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationResult

        result = BudgetAllocationResult()
        assert result.allowed is False
        assert result.enforcement_level == "none"
        assert result.consumed_pct == 0.0
        assert result.reason is None

    def test_denied_result(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationResult

        result = BudgetAllocationResult(
            allowed=False,
            enforcement_level="halt",
            consumed_pct=100.0,
            reason="budget exhausted",
        )
        assert result.allowed is False
        assert result.reason == "budget exhausted"

    def test_allowed_result(self) -> None:
        from economic_governor.temporal.workflows import BudgetAllocationResult

        result = BudgetAllocationResult(
            allowed=True,
            enforcement_level="none",
            consumed_pct=30.0,
        )
        assert result.allowed is True
        assert result.reason is None
