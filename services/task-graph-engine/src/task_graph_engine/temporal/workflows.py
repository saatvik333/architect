"""Temporal workflow definitions for task orchestration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from architect_common.enums import EvalVerdict, StatusEnum


TASK_QUEUE = "task-graph-engine"


@workflow.defn
class TaskOrchestrationWorkflow:
    """Main orchestration workflow for the Task Graph Engine.

    Orchestrates the full lifecycle:
    1. Decompose a spec into tasks.
    2. Build a DAG.
    3. Schedule ready tasks, execute via activities, evaluate results.
    4. Retry failures within budget, escalate hard failures.
    5. Complete when all tasks pass or budget is exhausted.
    """

    @workflow.run
    async def run(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Execute the full task orchestration loop.

        Args:
            spec: A project specification to decompose and execute.

        Returns:
            A summary dict with task results and final status.
        """
        # Step 1: Decompose the specification into tasks.
        raw_tasks: list[dict[str, Any]] = await workflow.execute_activity(
            "decompose_spec",
            args=[spec],
            start_to_close_timeout=timedelta(minutes=5),
        )

        task_ids = [t["id"] for t in raw_tasks]
        completed: set[str] = set()
        failed: set[str] = set()
        task_results: dict[str, dict[str, Any]] = {}

        # Main orchestration loop.
        max_iterations = len(task_ids) * 4  # Safety bound to prevent infinite loops.
        iteration = 0

        while len(completed) + len(failed) < len(task_ids) and iteration < max_iterations:
            iteration += 1

            # Step 2: Check budget before proceeding.
            budget_status: dict[str, Any] = await workflow.execute_activity(
                "check_budget",
                start_to_close_timeout=timedelta(seconds=30),
            )
            if budget_status.get("exhausted", False):
                workflow.logger.warning("Budget exhausted, stopping orchestration")
                break

            # Step 3: Get the next ready task.
            next_task: dict[str, Any] | None = await workflow.execute_activity(
                "schedule_next_task",
                start_to_close_timeout=timedelta(seconds=30),
            )

            if next_task is None:
                # No tasks ready — all remaining tasks may be blocked on failures.
                if failed:
                    workflow.logger.warning(
                        "No tasks ready and some have failed — stopping",
                    )
                    break
                # Otherwise wait a bit and retry (tasks may be in progress elsewhere).
                await workflow.sleep(timedelta(seconds=5))
                continue

            task_id = next_task["id"]

            # Step 4: Mark the task as running.
            await workflow.execute_activity(
                "update_task_status",
                args=[task_id, StatusEnum.RUNNING.value],
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 5: Execute the task (this is where the agent does its work).
            try:
                result: dict[str, Any] = await workflow.execute_activity(
                    "execute_task",
                    args=[next_task],
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=next_task.get("max_retries", 3),
                        initial_interval=timedelta(seconds=10),
                        backoff_coefficient=2.0,
                        maximum_interval=timedelta(minutes=5),
                    ),
                )
            except Exception as exc:
                # Task execution failed after all retries.
                await workflow.execute_activity(
                    "update_task_status",
                    args=[task_id, StatusEnum.FAILED.value],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                failed.add(task_id)
                task_results[task_id] = {
                    "status": StatusEnum.FAILED.value,
                    "error": str(exc),
                }
                workflow.logger.error("Task failed permanently", extra={"task_id": task_id})
                continue

            # Step 6: Evaluate the result.
            verdict = result.get("verdict", EvalVerdict.PASS.value)

            if verdict == EvalVerdict.PASS.value:
                await workflow.execute_activity(
                    "update_task_status",
                    args=[task_id, StatusEnum.COMPLETED.value],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                completed.add(task_id)
                task_results[task_id] = {
                    "status": StatusEnum.COMPLETED.value,
                    "verdict": verdict,
                }
            elif verdict == EvalVerdict.FAIL_HARD.value:
                # Hard failure — no retry.
                await workflow.execute_activity(
                    "update_task_status",
                    args=[task_id, StatusEnum.FAILED.value],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                failed.add(task_id)
                task_results[task_id] = {
                    "status": StatusEnum.FAILED.value,
                    "verdict": verdict,
                }
            else:
                # Soft failure — will be retried by the retry_policy on the activity.
                await workflow.execute_activity(
                    "update_task_status",
                    args=[task_id, StatusEnum.FAILED.value],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                failed.add(task_id)
                task_results[task_id] = {
                    "status": StatusEnum.FAILED.value,
                    "verdict": verdict,
                }

        # Build summary.
        all_passed = len(completed) == len(task_ids)
        return {
            "total_tasks": len(task_ids),
            "completed": len(completed),
            "failed": len(failed),
            "all_passed": all_passed,
            "task_results": task_results,
            "budget_status": budget_status if "budget_status" in dir() else {},
        }
