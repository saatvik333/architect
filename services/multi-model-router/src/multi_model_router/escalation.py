"""Failure-driven escalation policy for model tier upgrades."""

from __future__ import annotations

from architect_common.enums import ModelTier
from architect_common.types import TaskId
from multi_model_router.models import EscalationRecord

# ── Escalation chain: TIER_3 -> TIER_2 -> TIER_1 -> None (human) ────
_ESCALATION_CHAIN: dict[ModelTier, ModelTier | None] = {
    ModelTier.TIER_3: ModelTier.TIER_2,
    ModelTier.TIER_2: ModelTier.TIER_1,
    ModelTier.TIER_1: None,
}


class EscalationPolicy:
    """Track task failures and decide when to escalate to a higher tier."""

    def __init__(
        self,
        max_tier_failures: int = 2,
        max_total_failures: int = 5,
    ) -> None:
        self._max_tier_failures = max_tier_failures
        self._max_total_failures = max_total_failures
        self._records: dict[TaskId, EscalationRecord] = {}

    def record_failure(
        self,
        task_id: TaskId,
        current_tier: ModelTier,
    ) -> EscalationRecord:
        """Record a failure for *task_id* at *current_tier*.

        If the failure count at the current tier reaches the threshold,
        the task is automatically escalated to the next tier.
        """
        existing = self._records.get(task_id)
        failure_count = (existing.failure_count if existing else 0) + 1
        history = list(existing.escalation_history) if existing else []

        needs_human = failure_count >= self._max_total_failures

        # Count consecutive failures at the current tier
        tier_failures = 1
        for entry in reversed(history):
            if entry.get("tier") == current_tier.value:
                tier_failures += 1
            else:
                break

        # Check if we should escalate
        if tier_failures >= self._max_tier_failures:
            next_t = self.next_tier(current_tier)
            if next_t is None:
                needs_human = True
                new_tier = current_tier
            else:
                new_tier = next_t
            history = [
                *history,
                {
                    "tier": current_tier.value,
                    "reason": f"escalated after {tier_failures} failures",
                },
            ]
        else:
            new_tier = current_tier
            history = [
                *history,
                {"tier": current_tier.value, "reason": "failure recorded"},
            ]

        record = EscalationRecord(
            task_id=task_id,
            failure_count=failure_count,
            current_tier=new_tier,
            escalation_history=history,
            needs_human=needs_human,
        )
        self._records[task_id] = record
        return record

    def get_record(self, task_id: TaskId) -> EscalationRecord | None:
        """Return the escalation record for *task_id*, or ``None``."""
        return self._records.get(task_id)

    def should_escalate(self, task_id: TaskId) -> bool:
        """Return ``True`` if *task_id* should be escalated."""
        record = self._records.get(task_id)
        if record is None:
            return False

        # Count consecutive failures at the current tier
        tier_failures = 0
        for entry in reversed(record.escalation_history):
            if entry.get("tier") == record.current_tier.value:
                tier_failures += 1
            else:
                break

        return tier_failures >= self._max_tier_failures

    def next_tier(self, current: ModelTier) -> ModelTier | None:
        """Return the next tier in the escalation chain, or ``None`` for human."""
        return _ESCALATION_CHAIN.get(current)

    def reset(self, task_id: TaskId) -> None:
        """Clear all escalation state for *task_id*."""
        self._records.pop(task_id, None)
