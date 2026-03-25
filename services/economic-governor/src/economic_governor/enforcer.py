"""Enforcement engine — executes cost-control actions.

When the :class:`~economic_governor.budget_tracker.BudgetTracker` detects that
consumption crosses a threshold, the Enforcer takes concrete actions such as
publishing bus events, pausing tasks, or forcing a tier downgrade.
"""

from __future__ import annotations

import httpx

from architect_common.enums import EnforcementLevel, EventType, ModelTier
from architect_common.logging import get_logger
from architect_common.types import TaskId, _prefixed_uuid, utcnow
from architect_events.publisher import EventPublisher
from architect_events.schemas import (
    BudgetHaltEvent,
    BudgetTaskPausedEvent,
    BudgetThresholdAlertEvent,
    BudgetTierDowngradeEvent,
    EventEnvelope,
    SpinDetectedEvent,
)
from economic_governor.config import EconomicGovernorConfig
from economic_governor.models import BudgetSnapshot, EnforcementRecord, SpinDetection

logger = get_logger(component="economic_governor.enforcer")


class Enforcer:
    """Carries out enforcement actions against the ARCHITECT system."""

    def __init__(
        self,
        config: EconomicGovernorConfig,
        publisher: EventPublisher,
    ) -> None:
        self._config = config
        self._publisher = publisher
        self._client: httpx.AsyncClient | None = None
        self._history: list[EnforcementRecord] = []

    # ── Lifecycle ────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Create shared HTTP client for communicating with other services."""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        logger.info("enforcer HTTP client started")

    async def shutdown(self) -> None:
        """Close the shared HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("enforcer HTTP client stopped")

    # ── Enforcement actions ──────────────────────────────────────────

    async def enforce_alert(self, snapshot: BudgetSnapshot) -> None:
        """Publish a budget threshold alert event and log to history."""
        payload = BudgetThresholdAlertEvent(
            level=EnforcementLevel.ALERT,
            consumed_pct=snapshot.consumed_pct,
            consumed_tokens=snapshot.consumed_tokens,
            remaining_tokens=snapshot.allocated_tokens - snapshot.consumed_tokens,
            burn_rate_tokens_per_min=snapshot.burn_rate_tokens_per_min,
        )
        envelope = EventEnvelope(
            type=EventType.BUDGET_THRESHOLD_ALERT,
            payload=payload.model_dump(mode="json"),
        )
        await self._publisher.publish(envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=EnforcementLevel.ALERT,
            action_type="budget_alert",
            details={"consumed_pct": snapshot.consumed_pct},
            budget_consumed_pct=snapshot.consumed_pct,
        )
        self._history.append(record)
        logger.warning(
            "budget alert enforced",
            consumed_pct=snapshot.consumed_pct,
            burn_rate=snapshot.burn_rate_tokens_per_min,
        )

    async def enforce_restrict(self, snapshot: BudgetSnapshot) -> None:
        """Force a tier downgrade and pause non-critical tasks."""
        # Publish tier-downgrade event.
        tier_payload = BudgetTierDowngradeEvent(
            previous_max_tier=ModelTier.TIER_1,
            enforced_max_tier=ModelTier(self._config.restrict_max_tier),
            reason=f"Budget at {snapshot.consumed_pct}% — restricting to cheaper tiers",
        )
        tier_envelope = EventEnvelope(
            type=EventType.BUDGET_TIER_DOWNGRADE,
            payload=tier_payload.model_dump(mode="json"),
        )
        await self._publisher.publish(tier_envelope)

        # Notify task graph to pause non-critical work.
        pause_payload = BudgetTaskPausedEvent(
            task_id=TaskId("*"),
            reason=f"Budget restriction at {snapshot.consumed_pct}%",
        )
        pause_envelope = EventEnvelope(
            type=EventType.BUDGET_TASK_PAUSED,
            payload=pause_payload.model_dump(mode="json"),
        )
        await self._publisher.publish(pause_envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=EnforcementLevel.RESTRICT,
            action_type="budget_restrict",
            details={
                "consumed_pct": snapshot.consumed_pct,
                "enforced_max_tier": self._config.restrict_max_tier,
            },
            budget_consumed_pct=snapshot.consumed_pct,
        )
        self._history.append(record)
        logger.warning(
            "budget restriction enforced",
            consumed_pct=snapshot.consumed_pct,
            max_tier=self._config.restrict_max_tier,
        )

    async def enforce_halt(self, snapshot: BudgetSnapshot) -> None:
        """Cancel all tasks and halt all work."""
        halt_payload = BudgetHaltEvent(
            consumed_pct=snapshot.consumed_pct,
            tasks_cancelled=0,
            progress_report={
                "consumed_tokens": snapshot.consumed_tokens,
                "allocated_tokens": snapshot.allocated_tokens,
                "enforcement_level": snapshot.enforcement_level.value,
            },
        )
        halt_envelope = EventEnvelope(
            type=EventType.BUDGET_HALT,
            payload=halt_payload.model_dump(mode="json"),
        )
        await self._publisher.publish(halt_envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=EnforcementLevel.HALT,
            action_type="budget_halt",
            details={"consumed_pct": snapshot.consumed_pct},
            budget_consumed_pct=snapshot.consumed_pct,
        )
        self._history.append(record)
        logger.error(
            "budget halt enforced — all work stopped",
            consumed_pct=snapshot.consumed_pct,
        )

    async def kill_spinning_agent(self, detection: SpinDetection) -> None:
        """Terminate an agent that is spinning without progress."""
        spin_payload = SpinDetectedEvent(
            agent_id=detection.agent_id,
            task_id=detection.task_id,
            retry_count=detection.retry_count,
            tokens_wasted=detection.tokens_since_last_diff,
        )
        spin_envelope = EventEnvelope(
            type=EventType.BUDGET_SPIN_DETECTED,
            payload=spin_payload.model_dump(mode="json"),
        )
        await self._publisher.publish(spin_envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=EnforcementLevel.RESTRICT,
            action_type="spin_kill",
            target_id=str(detection.agent_id),
            details={
                "task_id": str(detection.task_id),
                "retry_count": detection.retry_count,
                "tokens_wasted": detection.tokens_since_last_diff,
            },
            budget_consumed_pct=0.0,
            timestamp=utcnow(),
        )
        self._history.append(record)
        logger.warning(
            "spinning agent killed",
            agent_id=str(detection.agent_id),
            task_id=str(detection.task_id),
            retries=detection.retry_count,
        )

    # ── Query ────────────────────────────────────────────────────────

    def get_history(self) -> list[EnforcementRecord]:
        """Return the full enforcement action history."""
        return list(self._history)
