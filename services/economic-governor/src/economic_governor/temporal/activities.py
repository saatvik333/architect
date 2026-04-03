"""Temporal activity definitions for the Economic Governor.

Activities are defined as methods on :class:`BudgetActivities` so that the
Temporal worker can inject shared :class:`BudgetTracker` and
:class:`EfficiencyScorer` singletons.  This avoids the previous bug where
every activity call created a fresh tracker (always seeing zero consumption).
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import BudgetPhase, EnforcementLevel
from architect_common.logging import get_logger
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.efficiency_scorer import EfficiencyScorer

logger = get_logger(component="economic_governor.temporal.activities")


class BudgetActivities:
    """Temporal activities that operate on shared Economic Governor state."""

    def __init__(
        self,
        budget_tracker: BudgetTracker,
        efficiency_scorer: EfficiencyScorer,
    ) -> None:
        self._tracker = budget_tracker
        self._scorer = efficiency_scorer

    @activity.defn
    async def get_budget_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return the current budget snapshot as a dict.

        Args:
            params: Unused -- present for Temporal activity signature compatibility.

        Returns:
            Serialised :class:`BudgetSnapshot`.
        """
        activity.logger.info("get_budget_status activity started")
        snapshot = await self._tracker.get_snapshot()
        return snapshot.model_dump(mode="json")

    @activity.defn
    async def check_budget_for_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Check whether a task can proceed given the current budget.

        Args:
            task_data: Dict with ``estimated_tokens`` key.

        Returns:
            Dict with ``allowed`` (bool), ``enforcement_level``, and ``consumed_pct``.
        """
        activity.logger.info("check_budget_for_task activity started")

        estimated_tokens = task_data.get("estimated_tokens", 0)
        snapshot = await self._tracker.get_snapshot()

        remaining = snapshot.allocated_tokens - snapshot.consumed_tokens
        allowed = (
            remaining >= estimated_tokens and snapshot.enforcement_level != EnforcementLevel.HALT
        )

        return {
            "allowed": allowed,
            "enforcement_level": snapshot.enforcement_level,
            "consumed_pct": snapshot.consumed_pct,
            "remaining_tokens": remaining,
        }

    @activity.defn
    async def record_consumption(self, consumption_data: dict[str, Any]) -> dict[str, Any]:
        """Record token consumption via a Temporal activity.

        Args:
            consumption_data: Dict with ``agent_id``, ``tokens``, ``cost_usd``, optional ``phase``.

        Returns:
            Dict with the resulting ``enforcement_level``.
        """
        activity.logger.info("record_consumption activity started")

        agent_id = consumption_data.get("agent_id", "unknown")
        tokens = int(consumption_data.get("tokens", 0))
        cost_usd = float(consumption_data.get("cost_usd", 0.0))
        phase_str = consumption_data.get("phase", "implementation")
        try:
            phase = BudgetPhase(phase_str)
        except ValueError:
            phase = BudgetPhase.IMPLEMENTATION

        level = await self._tracker.record_consumption(
            agent_id=agent_id,
            tokens=tokens,
            cost_usd=cost_usd,
            phase=phase,
        )
        return {"enforcement_level": level.value}

    @activity.defn
    async def compute_efficiency_scores(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compute and return the efficiency leaderboard.

        Args:
            params: Unused -- present for Temporal activity signature compatibility.

        Returns:
            Serialised :class:`EfficiencyLeaderboard`.
        """
        activity.logger.info("compute_efficiency_scores activity started")
        leaderboard = await self._scorer.compute_scores()
        return leaderboard.model_dump(mode="json")

    @activity.defn
    async def enforce_budget(self, enforcement_data: dict[str, Any]) -> dict[str, Any]:
        """Execute an enforcement action based on the current budget state.

        Args:
            enforcement_data: Dict with ``level`` (enforcement level string).

        Returns:
            Dict with ``action_taken`` and ``level``.
        """
        activity.logger.info("enforce_budget activity started")
        level = enforcement_data.get("level", "none")
        return {
            "action_taken": level != "none",
            "level": level,
        }
