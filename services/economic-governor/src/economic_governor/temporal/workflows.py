"""Temporal workflow definitions for the Economic Governor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from architect_common.enums import EnforcementLevel


TASK_QUEUE = "economic-governor"

# Activity name constants — these correspond to methods on
# ``economic_governor.temporal.activities.BudgetActivities``.
# The Temporal Python SDK requires string names (not direct method references)
# when activities are defined as methods on a class instance.
ACT_GET_BUDGET_STATUS = "get_budget_status"  # BudgetActivities.get_budget_status
ACT_ENFORCE_BUDGET = "enforce_budget"  # BudgetActivities.enforce_budget
ACT_COMPUTE_EFFICIENCY = "compute_efficiency_scores"  # BudgetActivities.compute_efficiency_scores
ACT_CHECK_BUDGET_FOR_TASK = "check_budget_for_task"  # BudgetActivities.check_budget_for_task
ACT_RECORD_CONSUMPTION = "record_consumption"  # BudgetActivities.record_consumption


# ── Typed workflow parameters ────────────────────────────────────────


@dataclass
class BudgetMonitoringParams:
    """Input parameters for the budget monitoring workflow."""

    poll_interval_seconds: int = 60
    efficiency_interval_seconds: int = 300
    max_iterations: int = 1000


@dataclass
class BudgetMonitoringResult:
    """Output of the budget monitoring workflow."""

    iterations_completed: int = 0
    final_level: str = "none"
    completed: bool = False


@dataclass
class BudgetAllocationParams:
    """Input parameters for the budget allocation workflow."""

    task_id: str = ""
    estimated_tokens: int = 0
    agent_id: str = "unknown"
    cost_usd: float = 0.0


@dataclass
class BudgetAllocationResult:
    """Output of the budget allocation workflow."""

    allowed: bool = False
    enforcement_level: str = "none"
    consumed_pct: float = 0.0
    reason: str | None = None


@workflow.defn
class BudgetMonitoringWorkflow:
    """Long-running periodic workflow that monitors budget consumption.

    Periodically checks the budget status and triggers enforcement
    actions when thresholds are crossed.
    """

    @workflow.run
    async def run(self, params: BudgetMonitoringParams | dict[str, Any]) -> BudgetMonitoringResult:
        """Execute the budget monitoring loop.

        Args:
            params: Typed :class:`BudgetMonitoringParams` or a dict for
                    backwards compatibility.

        Returns:
            :class:`BudgetMonitoringResult` with iteration count and final status.
        """
        if isinstance(params, dict):
            params = BudgetMonitoringParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in BudgetMonitoringParams.__dataclass_fields__
                }
            )

        poll_interval = params.poll_interval_seconds
        efficiency_every = params.efficiency_interval_seconds // max(poll_interval, 1)
        max_iterations = params.max_iterations
        iterations = 0
        enforcement_level: str = EnforcementLevel.NONE

        while iterations < max_iterations:
            iterations += 1

            # Fetch current budget status.
            status: dict[str, Any] = await workflow.execute_activity(
                ACT_GET_BUDGET_STATUS,
                args=[{}],
                start_to_close_timeout=timedelta(seconds=30),
            )

            enforcement_level = status.get("enforcement_level", EnforcementLevel.NONE)

            # If enforcement is needed, execute it.
            if enforcement_level != EnforcementLevel.NONE:
                await workflow.execute_activity(
                    ACT_ENFORCE_BUDGET,
                    args=[{"level": enforcement_level}],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # If halted, stop the monitoring loop.
            if enforcement_level == EnforcementLevel.HALT:
                workflow.logger.warning("Budget halted — stopping monitoring workflow")
                break

            # Periodically recompute efficiency scores.
            if iterations % max(efficiency_every, 1) == 0:
                await workflow.execute_activity(
                    ACT_COMPUTE_EFFICIENCY,
                    args=[{}],
                    start_to_close_timeout=timedelta(seconds=60),
                )

            await workflow.sleep(timedelta(seconds=poll_interval))

        return BudgetMonitoringResult(
            iterations_completed=iterations,
            final_level=str(enforcement_level),
            completed=iterations >= max_iterations,
        )


@workflow.defn
class BudgetAllocationWorkflow:
    """One-shot workflow that checks budget feasibility for a task.

    Validates that sufficient budget remains and records the consumption
    if the task proceeds.
    """

    @workflow.run
    async def run(
        self, task_data: BudgetAllocationParams | dict[str, Any]
    ) -> BudgetAllocationResult:
        """Check budget and optionally record consumption.

        Args:
            task_data: Typed :class:`BudgetAllocationParams` or a dict for
                       backwards compatibility.

        Returns:
            :class:`BudgetAllocationResult` with allowed flag and budget info.
        """
        if isinstance(task_data, dict):
            task_data = BudgetAllocationParams(
                **{
                    k: v
                    for k, v in task_data.items()
                    if k in BudgetAllocationParams.__dataclass_fields__
                }
            )

        # Step 1: Check if the task can proceed.
        check_result: dict[str, Any] = await workflow.execute_activity(
            ACT_CHECK_BUDGET_FOR_TASK,
            args=[
                {
                    "task_id": task_data.task_id,
                    "estimated_tokens": task_data.estimated_tokens,
                }
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if not check_result.get("allowed", False):
            return BudgetAllocationResult(
                allowed=False,
                enforcement_level=check_result.get("enforcement_level", "halt"),
                consumed_pct=check_result.get("consumed_pct", 0.0),
                reason="insufficient budget or budget halted",
            )

        # Step 2: Record the anticipated consumption.
        consumption_result: dict[str, Any] = await workflow.execute_activity(
            ACT_RECORD_CONSUMPTION,
            args=[
                {
                    "agent_id": task_data.agent_id,
                    "tokens": task_data.estimated_tokens,
                    "cost_usd": task_data.cost_usd,
                }
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return BudgetAllocationResult(
            allowed=True,
            enforcement_level=consumption_result.get("enforcement_level", "none"),
            consumed_pct=check_result.get("consumed_pct", 0.0),
        )
