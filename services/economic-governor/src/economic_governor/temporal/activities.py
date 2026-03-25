"""Temporal activity definitions for the Economic Governor."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import EnforcementLevel
from architect_common.logging import get_logger
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer

logger = get_logger(component="economic_governor.temporal.activities")


@activity.defn
async def get_budget_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return the current budget snapshot as a dict.

    Args:
        params: Unused — present for Temporal activity signature compatibility.

    Returns:
        Serialised :class:`BudgetSnapshot`.
    """
    activity.logger.info("get_budget_status activity started")
    config = EconomicGovernorConfig()
    tracker = BudgetTracker(config)
    snapshot = tracker.get_snapshot()
    return snapshot.model_dump(mode="json")


@activity.defn
async def check_budget_for_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """Check whether a task can proceed given the current budget.

    Args:
        task_data: Dict with ``estimated_tokens`` key.

    Returns:
        Dict with ``allowed`` (bool), ``enforcement_level``, and ``consumed_pct``.
    """
    activity.logger.info("check_budget_for_task activity started")
    config = EconomicGovernorConfig()
    tracker = BudgetTracker(config)

    estimated_tokens = task_data.get("estimated_tokens", 0)
    snapshot = tracker.get_snapshot()

    remaining = snapshot.allocated_tokens - snapshot.consumed_tokens
    allowed = remaining >= estimated_tokens and snapshot.enforcement_level != EnforcementLevel.HALT

    return {
        "allowed": allowed,
        "enforcement_level": snapshot.enforcement_level,
        "consumed_pct": snapshot.consumed_pct,
        "remaining_tokens": remaining,
    }


@activity.defn
async def record_consumption(consumption_data: dict[str, Any]) -> dict[str, Any]:
    """Record token consumption via a Temporal activity.

    Args:
        consumption_data: Dict with ``agent_id``, ``tokens``, ``cost_usd``.

    Returns:
        Dict with the resulting ``enforcement_level``.
    """
    activity.logger.info("record_consumption activity started")
    config = EconomicGovernorConfig()
    tracker = BudgetTracker(config)

    agent_id = consumption_data.get("agent_id", "unknown")
    tokens = consumption_data.get("tokens", 0)
    cost_usd = consumption_data.get("cost_usd", 0.0)

    level = tracker.record_consumption(agent_id=agent_id, tokens=tokens, cost_usd=cost_usd)
    return {"enforcement_level": level.value}


@activity.defn
async def compute_efficiency_scores(params: dict[str, Any]) -> dict[str, Any]:
    """Compute and return the efficiency leaderboard.

    Args:
        params: Unused — present for Temporal activity signature compatibility.

    Returns:
        Serialised :class:`EfficiencyLeaderboard`.
    """
    activity.logger.info("compute_efficiency_scores activity started")
    scorer = EfficiencyScorer()
    leaderboard = scorer.compute_scores()
    return leaderboard.model_dump(mode="json")


@activity.defn
async def enforce_budget(enforcement_data: dict[str, Any]) -> dict[str, Any]:
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
