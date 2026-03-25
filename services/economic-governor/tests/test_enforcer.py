"""Tests for the Enforcer."""

from __future__ import annotations

from unittest.mock import AsyncMock

from architect_common.enums import EnforcementLevel
from architect_common.types import AgentId, TaskId
from economic_governor.enforcer import Enforcer
from economic_governor.models import BudgetSnapshot, SpinDetection


class TestEnforcer:
    """Unit tests for enforcement actions (mocked HTTP + events)."""

    async def test_enforce_alert_publishes_event(
        self, enforcer: Enforcer, mock_publisher: AsyncMock
    ) -> None:
        """enforce_alert should publish a BudgetThresholdAlertEvent."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=8_500_000,
            consumed_pct=85.0,
            burn_rate_tokens_per_min=1000.0,
            enforcement_level=EnforcementLevel.ALERT,
        )
        await enforcer.enforce_alert(snapshot)

        mock_publisher.publish.assert_called_once()
        envelope = mock_publisher.publish.call_args[0][0]
        assert envelope.type == "budget.threshold_alert"

    async def test_enforce_alert_records_history(self, enforcer: Enforcer) -> None:
        """enforce_alert should add an entry to the history."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=8_500_000,
            consumed_pct=85.0,
            enforcement_level=EnforcementLevel.ALERT,
        )
        await enforcer.enforce_alert(snapshot)

        history = enforcer.get_history()
        assert len(history) == 1
        assert history[0].level == EnforcementLevel.ALERT
        assert history[0].action_type == "budget_alert"

    async def test_enforce_restrict_publishes_two_events(
        self, enforcer: Enforcer, mock_publisher: AsyncMock
    ) -> None:
        """enforce_restrict should publish tier-downgrade and task-paused events."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=9_600_000,
            consumed_pct=96.0,
            enforcement_level=EnforcementLevel.RESTRICT,
        )
        await enforcer.enforce_restrict(snapshot)

        # Two events: tier downgrade + task paused.
        assert mock_publisher.publish.call_count == 2

    async def test_enforce_halt_publishes_event(
        self, enforcer: Enforcer, mock_publisher: AsyncMock
    ) -> None:
        """enforce_halt should publish a BudgetHaltEvent."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=10_000_000,
            consumed_pct=100.0,
            enforcement_level=EnforcementLevel.HALT,
        )
        await enforcer.enforce_halt(snapshot)

        mock_publisher.publish.assert_called_once()
        envelope = mock_publisher.publish.call_args[0][0]
        assert envelope.type == "budget.halt"

    async def test_enforce_halt_records_history(self, enforcer: Enforcer) -> None:
        """enforce_halt should add a HALT entry to history."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=10_000_000,
            consumed_pct=100.0,
            enforcement_level=EnforcementLevel.HALT,
        )
        await enforcer.enforce_halt(snapshot)

        history = enforcer.get_history()
        assert len(history) == 1
        assert history[0].level == EnforcementLevel.HALT

    async def test_kill_spinning_agent_publishes_event(
        self, enforcer: Enforcer, mock_publisher: AsyncMock
    ) -> None:
        """kill_spinning_agent should publish a SpinDetectedEvent."""
        detection = SpinDetection(
            agent_id=AgentId("agent-spinner"),
            task_id=TaskId("task-stuck"),
            is_spinning=True,
            retry_count=5,
            tokens_since_last_diff=15000,
        )
        await enforcer.kill_spinning_agent(detection)

        mock_publisher.publish.assert_called_once()
        envelope = mock_publisher.publish.call_args[0][0]
        assert envelope.type == "budget.spin_detected"

    async def test_history_accumulates(self, enforcer: Enforcer, mock_publisher: AsyncMock) -> None:
        """Multiple enforcement actions should all appear in history."""
        snapshot = BudgetSnapshot(
            allocated_tokens=10_000_000,
            consumed_tokens=8_500_000,
            consumed_pct=85.0,
            enforcement_level=EnforcementLevel.ALERT,
        )
        await enforcer.enforce_alert(snapshot)
        await enforcer.enforce_alert(snapshot)

        history = enforcer.get_history()
        assert len(history) == 2

    async def test_startup_shutdown_lifecycle(self, enforcer: Enforcer) -> None:
        """startup/shutdown should manage the HTTP client lifecycle."""
        await enforcer.startup()
        assert enforcer._client is not None

        await enforcer.shutdown()
        assert enforcer._client is None
