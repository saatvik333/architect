"""Monitoring glue layer.

Bridges event-bus callbacks to the budget tracker, spin detector,
efficiency scorer and enforcer. Also runs a periodic background loop
for polling external services.
"""

from __future__ import annotations

import asyncio

from architect_common.enums import EnforcementLevel
from architect_common.logging import get_logger
from architect_common.types import AgentId, TaskId
from architect_events.schemas import EventEnvelope
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer
from economic_governor.spin_detector import SpinDetector

logger = get_logger(component="economic_governor.monitor")


class Monitor:
    """Coordinates event handling and periodic monitoring tasks."""

    def __init__(
        self,
        config: EconomicGovernorConfig,
        budget_tracker: BudgetTracker,
        spin_detector: SpinDetector,
        efficiency_scorer: EfficiencyScorer,
        enforcer: Enforcer,
    ) -> None:
        self._config = config
        self._budget = budget_tracker
        self._spin = spin_detector
        self._efficiency = efficiency_scorer
        self._enforcer = enforcer
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ── Event handlers ───────────────────────────────────────────────

    async def handle_agent_completed(self, event: EventEnvelope) -> None:
        """Handle AGENT_COMPLETED events — record token consumption and check thresholds."""
        payload = event.payload
        agent_id = AgentId(str(payload.get("agent_id", "")))
        tokens = int(payload.get("tokens_consumed", 0))
        cost_usd = float(payload.get("cost_usd", 0.0))

        level = self._budget.record_consumption(
            agent_id=str(agent_id), tokens=tokens, cost_usd=cost_usd
        )
        await self._enforce_if_needed(level)

        logger.debug(
            "agent completed recorded",
            agent_id=str(agent_id),
            tokens=tokens,
            level=level,
        )

    async def handle_routing_decision(self, event: EventEnvelope) -> None:
        """Handle ROUTING_DECISION events — track routing cost."""
        payload = event.payload
        cost_usd = float(payload.get("cost_usd", 0.0))
        tokens = int(payload.get("input_tokens", 0)) + int(payload.get("output_tokens", 0))
        agent_id = str(payload.get("agent_id", "router"))

        if tokens > 0 or cost_usd > 0:
            level = self._budget.record_consumption(
                agent_id=agent_id, tokens=tokens, cost_usd=cost_usd
            )
            await self._enforce_if_needed(level)

    async def handle_task_completed(self, event: EventEnvelope) -> None:
        """Handle TASK_COMPLETED events — feed efficiency scorer."""
        payload = event.payload
        agent_id = AgentId(str(payload.get("agent_id", "")))
        quality = 1.0 if str(payload.get("verdict", "pass")) == "pass" else 0.5
        tokens = int(payload.get("tokens_consumed", 0))
        cost_usd = float(payload.get("cost_usd", 0.0))

        self._efficiency.record_task_completed(
            agent_id=agent_id,
            quality_score=quality,
            tokens=tokens,
            cost_usd=cost_usd,
        )

    async def handle_task_failed(self, event: EventEnvelope) -> None:
        """Handle TASK_FAILED events — check for spin behaviour."""
        payload = event.payload
        agent_id = AgentId(str(payload.get("agent_id", "")))
        task_id = TaskId(str(payload.get("task_id", "")))
        tokens = int(payload.get("tokens_consumed", 0))
        cost_usd = float(payload.get("cost_usd", 0.0))
        has_diff = bool(payload.get("has_diff", False))

        self._efficiency.record_task_failed(agent_id=agent_id, tokens=tokens, cost_usd=cost_usd)

        detection = self._spin.record_retry(
            agent_id=agent_id,
            task_id=task_id,
            has_diff=has_diff,
            tokens=tokens,
        )

        if detection.is_spinning:
            await self._enforcer.kill_spinning_agent(detection)

    # ── Periodic monitoring loop ─────────────────────────────────────

    async def run_monitoring_loop(self) -> None:
        """Background loop that periodically checks budget and recalculates efficiency."""
        self._running = True
        poll_interval = self._config.budget_poll_interval_seconds
        efficiency_interval = self._config.efficiency_recalc_interval_seconds
        efficiency_counter = 0

        logger.info(
            "monitoring loop started",
            poll_interval=poll_interval,
            efficiency_interval=efficiency_interval,
        )

        while self._running:
            try:
                await asyncio.sleep(poll_interval)

                # Check thresholds.
                new_level = self._budget.threshold_crossed()
                if new_level is not None:
                    await self._enforce_if_needed(new_level)

                # Periodically recalculate efficiency scores.
                efficiency_counter += poll_interval
                if efficiency_counter >= efficiency_interval:
                    efficiency_counter = 0
                    leaderboard = self._efficiency.compute_scores()
                    await self._efficiency.persist_scores(leaderboard)
                    logger.debug(
                        "efficiency scores recalculated",
                        agents=len(leaderboard.entries),
                    )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("error in monitoring loop")
                await asyncio.sleep(1)

        logger.info("monitoring loop stopped")

    def start(self) -> asyncio.Task[None]:
        """Spawn the monitoring loop as a background task."""
        self._task = asyncio.create_task(self.run_monitoring_loop())
        return self._task

    def stop(self) -> None:
        """Signal the monitoring loop to stop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()

    # ── Internals ────────────────────────────────────────────────────

    async def _enforce_if_needed(self, level: EnforcementLevel) -> None:
        """Execute the appropriate enforcement action for the given level."""
        snapshot = self._budget.get_snapshot()
        if level == EnforcementLevel.ALERT:
            await self._enforcer.enforce_alert(snapshot)
        elif level == EnforcementLevel.RESTRICT:
            await self._enforcer.enforce_restrict(snapshot)
        elif level == EnforcementLevel.HALT:
            await self._enforcer.enforce_halt(snapshot)
