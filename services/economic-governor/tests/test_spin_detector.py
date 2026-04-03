"""Tests for the SpinDetector."""

from __future__ import annotations

from architect_common.types import AgentId, TaskId
from economic_governor.config import EconomicGovernorConfig
from economic_governor.spin_detector import SpinDetector


class TestSpinDetector:
    """Unit tests for spin detection logic."""

    async def test_no_spin_on_first_retry(self, spin_detector: SpinDetector) -> None:
        """A single retry should not trigger spin detection."""
        result = await spin_detector.record_retry(
            agent_id=AgentId("agent-1"),
            task_id=TaskId("task-1"),
            has_diff=False,
            tokens=1000,
        )
        assert result.is_spinning is False
        assert result.retry_count == 1

    async def test_spin_after_max_retries(self, config: EconomicGovernorConfig) -> None:
        """Should detect spinning after max_retries retries without diff."""
        detector = SpinDetector(config)
        agent = AgentId("agent-spin")
        task = TaskId("task-spin")

        for _i in range(config.spin_max_retries):
            result = await detector.record_retry(
                agent_id=agent, task_id=task, has_diff=False, tokens=500
            )

        assert result.is_spinning is True
        assert result.retry_count == config.spin_max_retries
        assert result.tokens_since_last_diff == 500 * config.spin_max_retries

    async def test_diff_resets_counter(self, spin_detector: SpinDetector) -> None:
        """A successful diff should reset the spin counter."""
        agent = AgentId("agent-reset")
        task = TaskId("task-reset")

        # Two retries without diff.
        await spin_detector.record_retry(agent_id=agent, task_id=task, has_diff=False, tokens=500)
        await spin_detector.record_retry(agent_id=agent, task_id=task, has_diff=False, tokens=500)

        # Diff produced — should reset.
        result = await spin_detector.record_retry(
            agent_id=agent, task_id=task, has_diff=True, tokens=300
        )
        assert result.is_spinning is False
        assert result.retry_count == 0
        assert result.tokens_since_last_diff == 0

    async def test_independent_tracking_per_task(self, spin_detector: SpinDetector) -> None:
        """Spin tracking should be independent per (agent, task) pair."""
        agent = AgentId("agent-multi")
        task_a = TaskId("task-a")
        task_b = TaskId("task-b")

        await spin_detector.record_retry(agent_id=agent, task_id=task_a, has_diff=False, tokens=100)
        await spin_detector.record_retry(agent_id=agent, task_id=task_a, has_diff=False, tokens=100)

        result_b = await spin_detector.record_retry(
            agent_id=agent, task_id=task_b, has_diff=False, tokens=100
        )
        # Task B should be at retry 1, not 3.
        assert result_b.retry_count == 1
        assert result_b.is_spinning is False

    async def test_reset_clears_all_tasks_for_agent(self, spin_detector: SpinDetector) -> None:
        """reset() should clear all spin state for the given agent."""
        agent = AgentId("agent-clear")
        task = TaskId("task-clear")

        await spin_detector.record_retry(agent_id=agent, task_id=task, has_diff=False, tokens=100)
        await spin_detector.record_retry(agent_id=agent, task_id=task, has_diff=False, tokens=100)

        await spin_detector.reset(agent)

        # After reset, next retry should start from 1.
        result = await spin_detector.record_retry(
            agent_id=agent, task_id=task, has_diff=False, tokens=100
        )
        assert result.retry_count == 1

    async def test_tokens_accumulated_across_retries(self, spin_detector: SpinDetector) -> None:
        """Tokens should accumulate across retries without a diff."""
        agent = AgentId("agent-acc")
        task = TaskId("task-acc")

        await spin_detector.record_retry(agent_id=agent, task_id=task, has_diff=False, tokens=1000)
        result = await spin_detector.record_retry(
            agent_id=agent, task_id=task, has_diff=False, tokens=2000
        )

        assert result.tokens_since_last_diff == 3000
