"""Tests for the economic governor Monitor."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EnforcementLevel, EventType
from architect_common.types import AgentId, TaskId
from architect_events.schemas import EventEnvelope
from economic_governor.config import EconomicGovernorConfig
from economic_governor.models import SpinDetection
from economic_governor.monitor import Monitor


class TestMonitor:
    """Tests for Monitor event handling and lifecycle."""

    @pytest.fixture
    def mock_budget(self) -> AsyncMock:
        """Create a mock BudgetTracker."""
        tracker = AsyncMock()
        tracker.record_consumption = AsyncMock(return_value=EnforcementLevel.NONE)
        tracker.get_snapshot = AsyncMock()
        tracker.threshold_crossed = AsyncMock(return_value=None)
        return tracker

    @pytest.fixture
    def mock_spin(self) -> AsyncMock:
        """Create a mock SpinDetector."""
        detector = AsyncMock()
        detector.record_retry = AsyncMock(
            return_value=SpinDetection(
                agent_id=AgentId("agent-1"),
                task_id=TaskId("task-1"),
                is_spinning=False,
            )
        )
        return detector

    @pytest.fixture
    def mock_efficiency(self) -> AsyncMock:
        """Create a mock EfficiencyScorer."""
        return AsyncMock()

    @pytest.fixture
    def mock_enforcer(self) -> AsyncMock:
        """Create a mock Enforcer."""
        return AsyncMock()

    @pytest.fixture
    def monitor(
        self,
        config: EconomicGovernorConfig,
        mock_budget: AsyncMock,
        mock_spin: AsyncMock,
        mock_efficiency: AsyncMock,
        mock_enforcer: AsyncMock,
    ) -> Monitor:
        """Create a Monitor with mocked dependencies."""
        return Monitor(
            config=config,
            budget_tracker=mock_budget,
            spin_detector=mock_spin,
            efficiency_scorer=mock_efficiency,
            enforcer=mock_enforcer,
        )

    def _make_envelope(self, event_type: EventType, payload: dict) -> EventEnvelope:
        """Helper to create an EventEnvelope."""
        return EventEnvelope(type=event_type, payload=payload)

    # ── handle_agent_completed ───────────────────────────────────────

    async def test_handle_agent_completed_records_consumption(
        self, monitor: Monitor, mock_budget: AsyncMock
    ) -> None:
        """handle_agent_completed records consumption to budget tracker."""
        envelope = self._make_envelope(
            EventType.AGENT_COMPLETED,
            {"agent_id": "agent-001", "tokens_consumed": 500, "cost_usd": 0.005},
        )

        await monitor.handle_agent_completed(envelope)

        mock_budget.record_consumption.assert_called_once_with(
            agent_id="agent-001", tokens=500, cost_usd=0.005
        )

    async def test_handle_agent_completed_malformed_payload(
        self, monitor: Monitor, mock_budget: AsyncMock
    ) -> None:
        """handle_agent_completed with missing fields rejects with warning."""
        envelope = self._make_envelope(
            EventType.AGENT_COMPLETED,
            {"tokens_consumed": 500},  # missing agent_id
        )

        await monitor.handle_agent_completed(envelope)

        mock_budget.record_consumption.assert_not_called()

    async def test_handle_agent_completed_negative_tokens(
        self, monitor: Monitor, mock_budget: AsyncMock
    ) -> None:
        """handle_agent_completed with negative tokens rejects with warning."""
        envelope = self._make_envelope(
            EventType.AGENT_COMPLETED,
            {"agent_id": "agent-001", "tokens_consumed": -100, "cost_usd": 0.001},
        )

        await monitor.handle_agent_completed(envelope)

        mock_budget.record_consumption.assert_not_called()

    # ── handle_task_completed ────────────────────────────────────────

    async def test_handle_task_completed_records_to_efficiency(
        self, monitor: Monitor, mock_efficiency: AsyncMock
    ) -> None:
        """handle_task_completed records to efficiency scorer."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {
                "agent_id": "agent-002",
                "quality_score": 0.95,
                "verdict": "pass",
                "tokens_consumed": 200,
                "cost_usd": 0.002,
            },
        )

        await monitor.handle_task_completed(envelope)

        mock_efficiency.record_task_completed.assert_called_once_with(
            agent_id=AgentId("agent-002"),
            quality_score=1.0,  # verdict == "pass" -> quality 1.0
            tokens=200,
            cost_usd=0.002,
        )

    async def test_handle_task_completed_fail_verdict(
        self, monitor: Monitor, mock_efficiency: AsyncMock
    ) -> None:
        """handle_task_completed with non-pass verdict uses quality 0.5."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"agent_id": "agent-002", "verdict": "fail"},
        )

        await monitor.handle_task_completed(envelope)

        mock_efficiency.record_task_completed.assert_called_once()
        call_kwargs = mock_efficiency.record_task_completed.call_args.kwargs
        assert call_kwargs["quality_score"] == 0.5

    # ── handle_task_failed ───────────────────────────────────────────

    async def test_handle_task_failed_records_spin_and_efficiency(
        self, monitor: Monitor, mock_spin: AsyncMock, mock_efficiency: AsyncMock
    ) -> None:
        """handle_task_failed records to spin detector and efficiency scorer."""
        envelope = self._make_envelope(
            EventType.TASK_FAILED,
            {
                "agent_id": "agent-003",
                "task_id": "task-003",
                "tokens_consumed": 300,
                "has_diff": False,
                "cost_usd": 0.003,
            },
        )

        await monitor.handle_task_failed(envelope)

        mock_efficiency.record_task_failed.assert_called_once_with(
            agent_id=AgentId("agent-003"), tokens=300, cost_usd=0.003
        )
        mock_spin.record_retry.assert_called_once_with(
            agent_id=AgentId("agent-003"),
            task_id=TaskId("task-003"),
            has_diff=False,
            tokens=300,
        )

    async def test_handle_task_failed_malformed_payload(
        self, monitor: Monitor, mock_spin: AsyncMock, mock_efficiency: AsyncMock
    ) -> None:
        """handle_task_failed with missing fields rejects with warning."""
        envelope = self._make_envelope(
            EventType.TASK_FAILED,
            {"tokens_consumed": 100},  # missing agent_id and task_id
        )

        await monitor.handle_task_failed(envelope)

        mock_spin.record_retry.assert_not_called()
        mock_efficiency.record_task_failed.assert_not_called()

    async def test_handle_task_failed_spinning_agent(
        self,
        monitor: Monitor,
        mock_spin: AsyncMock,
        mock_enforcer: AsyncMock,
    ) -> None:
        """handle_task_failed kills spinning agent when spin detected."""
        spin_detection = SpinDetection(
            agent_id=AgentId("agent-003"),
            task_id=TaskId("task-003"),
            is_spinning=True,
            retry_count=5,
        )
        mock_spin.record_retry.return_value = spin_detection

        envelope = self._make_envelope(
            EventType.TASK_FAILED,
            {
                "agent_id": "agent-003",
                "task_id": "task-003",
                "tokens_consumed": 300,
                "has_diff": False,
                "cost_usd": 0.003,
            },
        )

        await monitor.handle_task_failed(envelope)

        mock_enforcer.kill_spinning_agent.assert_called_once_with(spin_detection)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def test_start_and_stop(self, monitor: Monitor) -> None:
        """Monitor start() spawns a task; stop() cancels it."""
        task = monitor.start()
        assert isinstance(task, asyncio.Task)
        assert not task.done()

        monitor.stop()
        # Give the event loop a chance to cancel
        await asyncio.sleep(0.05)
        assert task.done() or task.cancelled()

    async def test_stop_without_start(self, monitor: Monitor) -> None:
        """Monitor stop() without start should not raise."""
        monitor.stop()  # Should not raise
