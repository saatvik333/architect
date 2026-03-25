"""Temporal workflow definitions for the Economic Governor."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from architect_common.enums import EnforcementLevel
    from economic_governor.temporal.activities import (
        check_budget_for_task,
        compute_efficiency_scores,
        enforce_budget,
        get_budget_status,
        record_consumption,
    )


TASK_QUEUE = "economic-governor"


@workflow.defn
class BudgetMonitoringWorkflow:
    """Long-running periodic workflow that monitors budget consumption.

    Periodically checks the budget status and triggers enforcement
    actions when thresholds are crossed.
    """

    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the budget monitoring loop.

        Args:
            params: Dict with optional ``poll_interval_seconds`` (default 60)
                    and ``max_iterations`` (default 1000).

        Returns:
            Summary dict with iteration count and final status.
        """
        poll_interval = params.get("poll_interval_seconds", 60)
        max_iterations = params.get("max_iterations", 1000)
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # Fetch current budget status.
            status: dict[str, Any] = await workflow.execute_activity(
                get_budget_status,
                args=[{}],
                start_to_close_timeout=timedelta(seconds=30),
            )

            enforcement_level = status.get("enforcement_level", EnforcementLevel.NONE)

            # If enforcement is needed, execute it.
            if enforcement_level != EnforcementLevel.NONE:
                await workflow.execute_activity(
                    enforce_budget,
                    args=[{"level": enforcement_level}],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # If halted, stop the monitoring loop.
            if enforcement_level == EnforcementLevel.HALT:
                workflow.logger.warning("Budget halted — stopping monitoring workflow")
                break

            # Periodically recompute efficiency scores.
            if iterations % 10 == 0:
                await workflow.execute_activity(
                    compute_efficiency_scores,
                    args=[{}],
                    start_to_close_timeout=timedelta(seconds=60),
                )

            await workflow.sleep(timedelta(seconds=poll_interval))

        return {
            "iterations": iterations,
            "final_enforcement_level": enforcement_level,
            "completed": iterations >= max_iterations,
        }


@workflow.defn
class BudgetAllocationWorkflow:
    """One-shot workflow that checks budget feasibility for a task.

    Validates that sufficient budget remains and records the consumption
    if the task proceeds.
    """

    @workflow.run
    async def run(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Check budget and optionally record consumption.

        Args:
            task_data: Dict with ``task_id``, ``estimated_tokens``, and
                       optionally ``agent_id`` and ``cost_usd``.

        Returns:
            Dict with ``allowed``, ``enforcement_level``, and ``consumed_pct``.
        """
        # Step 1: Check if the task can proceed.
        check_result: dict[str, Any] = await workflow.execute_activity(
            check_budget_for_task,
            args=[task_data],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if not check_result.get("allowed", False):
            return {
                "allowed": False,
                "enforcement_level": check_result.get("enforcement_level", "halt"),
                "consumed_pct": check_result.get("consumed_pct", 0.0),
                "reason": "insufficient budget or budget halted",
            }

        # Step 2: Record the anticipated consumption.
        agent_id = task_data.get("agent_id", "unknown")
        tokens = task_data.get("estimated_tokens", 0)
        cost_usd = task_data.get("cost_usd", 0.0)

        consumption_result: dict[str, Any] = await workflow.execute_activity(
            record_consumption,
            args=[{"agent_id": agent_id, "tokens": tokens, "cost_usd": cost_usd}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "allowed": True,
            "enforcement_level": consumption_result.get("enforcement_level", "none"),
            "consumed_pct": check_result.get("consumed_pct", 0.0),
        }
