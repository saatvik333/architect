"""Enforcement engine — executes cost-control actions.

When the :class:`~economic_governor.budget_tracker.BudgetTracker` detects that
consumption crosses a threshold, the Enforcer takes concrete actions such as
publishing bus events, pausing tasks, or forcing a tier downgrade.
"""

from __future__ import annotations

from collections import deque

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import EnforcementLevel, EventType, ModelTier
from architect_common.logging import get_logger
from architect_common.types import ArchitectBase, TaskId, _prefixed_uuid
from architect_db.models.budget import EnforcementAction
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
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._config = config
        self._publisher = publisher
        self._session_factory = session_factory
        self._history: deque[EnforcementRecord] = deque(maxlen=1000)

    # ── Shared enforcement ceremony ───────────────────────────────────

    async def _enforce(
        self,
        level: EnforcementLevel,
        action_type: str,
        event_type: EventType,
        payload: ArchitectBase,
        details: dict[str, object],
        consumed_pct: float,
        target_id: str | None = None,
    ) -> None:
        """Shared enforcement ceremony: publish event, record, persist, log."""
        envelope = EventEnvelope(
            type=event_type,
            payload=payload.model_dump(mode="json"),
        )
        await self._publisher.publish(envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=level,
            action_type=action_type,
            target_id=target_id,
            details=details,
            budget_consumed_pct=consumed_pct,
        )
        self._history.append(record)
        await self._persist_action(record)

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
        await self._enforce(
            level=EnforcementLevel.ALERT,
            action_type="budget_alert",
            event_type=EventType.BUDGET_THRESHOLD_ALERT,
            payload=payload,
            details={"consumed_pct": snapshot.consumed_pct},
            consumed_pct=snapshot.consumed_pct,
        )
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
        await self._enforce(
            level=EnforcementLevel.RESTRICT,
            action_type="budget_tier_downgrade",
            event_type=EventType.BUDGET_TIER_DOWNGRADE,
            payload=tier_payload,
            details={
                "consumed_pct": snapshot.consumed_pct,
                "enforced_max_tier": self._config.restrict_max_tier,
            },
            consumed_pct=snapshot.consumed_pct,
        )

        # Notify task graph to pause non-critical work.
        pause_payload = BudgetTaskPausedEvent(
            task_id=TaskId("*"),
            reason=f"Budget restriction at {snapshot.consumed_pct}%",
        )
        await self._enforce(
            level=EnforcementLevel.RESTRICT,
            action_type="budget_restrict",
            event_type=EventType.BUDGET_TASK_PAUSED,
            payload=pause_payload,
            details={
                "consumed_pct": snapshot.consumed_pct,
                "enforced_max_tier": self._config.restrict_max_tier,
            },
            consumed_pct=snapshot.consumed_pct,
        )
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
        await self._enforce(
            level=EnforcementLevel.HALT,
            action_type="budget_halt",
            event_type=EventType.BUDGET_HALT,
            payload=halt_payload,
            details={"consumed_pct": snapshot.consumed_pct},
            consumed_pct=snapshot.consumed_pct,
        )
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
        await self._enforce(
            level=EnforcementLevel.RESTRICT,
            action_type="spin_kill",
            event_type=EventType.BUDGET_SPIN_DETECTED,
            payload=spin_payload,
            details={
                "task_id": str(detection.task_id),
                "retry_count": detection.retry_count,
                "tokens_wasted": detection.tokens_since_last_diff,
            },
            consumed_pct=0.0,
            target_id=str(detection.agent_id),
        )
        logger.warning(
            "spinning agent killed",
            agent_id=str(detection.agent_id),
            task_id=str(detection.task_id),
            retries=detection.retry_count,
        )

    # ── Persistence ──────────────────────────────────────────────────

    async def _persist_action(self, record: EnforcementRecord) -> None:
        """Write an :class:`EnforcementAction` row to Postgres.

        Failures are logged but never propagated — the in-memory history
        remains the authoritative fast path.
        """
        if self._session_factory is None:
            return
        try:
            action = EnforcementAction(
                enforcement_level=record.level,
                action_type=record.action_type,
                target_id=record.target_id,
                details=record.details,
                budget_consumed_pct=record.budget_consumed_pct,
            )
            async with self._session_factory() as session:
                session.add(action)
                await session.commit()
        except Exception:
            logger.warning("failed to persist enforcement action", exc_info=True)

    # ── Query ────────────────────────────────────────────────────────

    def get_history(self) -> list[EnforcementRecord]:
        """Return the full enforcement action history."""
        return list(self._history)
