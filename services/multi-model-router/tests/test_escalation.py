"""Tests for EscalationPolicy."""

from __future__ import annotations

from architect_common.enums import ModelTier
from architect_common.types import TaskId
from multi_model_router.escalation import EscalationPolicy


class TestEscalationPolicy:
    """Unit tests for the failure-driven escalation policy."""

    def test_first_failure_stays_at_tier(self, escalation_policy: EscalationPolicy) -> None:
        """A single failure should not escalate the task."""
        record = escalation_policy.record_failure(TaskId("task-esc00001"), ModelTier.TIER_3)
        assert record.failure_count == 1
        assert record.current_tier == ModelTier.TIER_3
        assert record.needs_human is False

    def test_second_failure_escalates(self, escalation_policy: EscalationPolicy) -> None:
        """Two failures at the same tier should trigger escalation."""
        task_id = TaskId("task-esc00002")
        escalation_policy.record_failure(task_id, ModelTier.TIER_3)
        record = escalation_policy.record_failure(task_id, ModelTier.TIER_3)
        assert record.current_tier == ModelTier.TIER_2
        assert record.failure_count == 2

    def test_escalation_chain_tier3_to_tier2_to_tier1_to_human(self) -> None:
        """Full escalation chain: TIER_3 -> TIER_2 -> TIER_1 -> human."""
        policy = EscalationPolicy(max_tier_failures=1, max_total_failures=10)
        task_id = TaskId("task-esc00003")

        # First failure at TIER_3 -> escalate to TIER_2
        record = policy.record_failure(task_id, ModelTier.TIER_3)
        assert record.current_tier == ModelTier.TIER_2

        # Failure at TIER_2 -> escalate to TIER_1
        record = policy.record_failure(task_id, ModelTier.TIER_2)
        assert record.current_tier == ModelTier.TIER_1

        # Failure at TIER_1 -> human escalation
        record = policy.record_failure(task_id, ModelTier.TIER_1)
        assert record.needs_human is True

    def test_reset_clears_state(self, escalation_policy: EscalationPolicy) -> None:
        """Resetting a task should remove all its escalation state."""
        task_id = TaskId("task-esc00004")
        escalation_policy.record_failure(task_id, ModelTier.TIER_3)
        assert escalation_policy.get_record(task_id) is not None

        escalation_policy.reset(task_id)
        assert escalation_policy.get_record(task_id) is None

    def test_max_total_failures_triggers_needs_human(self) -> None:
        """Reaching max_total_failures should set needs_human."""
        policy = EscalationPolicy(max_tier_failures=10, max_total_failures=3)
        task_id = TaskId("task-esc00005")

        policy.record_failure(task_id, ModelTier.TIER_3)
        policy.record_failure(task_id, ModelTier.TIER_3)
        record = policy.record_failure(task_id, ModelTier.TIER_3)
        assert record.needs_human is True
        assert record.failure_count == 3

    def test_get_record_unknown_task(self, escalation_policy: EscalationPolicy) -> None:
        """get_record for an unknown task should return None."""
        assert escalation_policy.get_record(TaskId("task-unknown")) is None

    def test_next_tier_returns_correct_chain(self, escalation_policy: EscalationPolicy) -> None:
        """next_tier should follow the escalation chain."""
        assert escalation_policy.next_tier(ModelTier.TIER_3) == ModelTier.TIER_2
        assert escalation_policy.next_tier(ModelTier.TIER_2) == ModelTier.TIER_1
        assert escalation_policy.next_tier(ModelTier.TIER_1) is None
