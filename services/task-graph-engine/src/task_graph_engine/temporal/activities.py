"""Temporal activity definitions for the Task Graph Engine."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.logging import get_logger

logger = get_logger(component="task_graph_activities")


@activity.defn
async def decompose_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Decompose a project specification into a list of task descriptors.

    This activity wraps :class:`TaskDecomposer` so that decomposition
    runs inside the Temporal activity execution context with proper
    heartbeating and timeout support.

    Args:
        spec: The project specification dictionary.

    Returns:
        A list of serialized task dictionaries.
    """
    from task_graph_engine.decomposer import TaskDecomposer
    from task_graph_engine.graph import TaskDAG

    decomposer = TaskDecomposer()
    tasks = await decomposer.decompose_spec(spec)

    # Build the DAG and validate it.
    dag = TaskDAG()
    for task in tasks:
        dag.add_task(task)
    for task in tasks:
        for dep_id in task.dependencies:
            dag.add_dependency(dep_id, task.id)

    errors = dag.validate()
    if errors:
        logger.warning("DAG validation warnings", errors=errors)

    # Return serializable dicts.
    return [task.model_dump(mode="json") for task in tasks]


@activity.defn
async def schedule_next_task() -> dict[str, Any] | None:
    """Get the next task that is ready to execute.

    This is a lightweight activity that queries the task repository
    for the highest-priority pending task.

    Returns:
        A serialized task dictionary, or ``None`` if no tasks are ready.
    """
    # In a full deployment, this would query the database through the scheduler.
    # For now, return None to signal no tasks (the workflow handles this gracefully).
    activity.heartbeat("checking for ready tasks")
    logger.info("schedule_next_task called")
    return None


@activity.defn
async def update_task_status(task_id: str, status: str) -> None:
    """Update the status of a task in the database.

    Args:
        task_id: The task identifier.
        status: The new status value.
    """
    activity.heartbeat(f"updating {task_id} to {status}")
    logger.info("Updating task status", task_id=task_id, status=status)
    # In a full deployment, this would call TaskRepository.update_status.
    # The actual persistence is handled when the scheduler is wired to a database.


@activity.defn
async def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    """Execute a task by dispatching to the appropriate agent.

    This is a placeholder that will be replaced with actual agent
    dispatch logic in later phases.

    Args:
        task: A serialized task dictionary.

    Returns:
        A result dictionary with at least a ``"verdict"`` key.
    """
    task_id = task.get("id", "unknown")
    task_type = task.get("type", "unknown")
    activity.heartbeat(f"executing {task_id} ({task_type})")
    logger.info("Executing task", task_id=task_id, task_type=task_type)

    # Placeholder: in production, this dispatches to a coding agent,
    # sandbox execution, and evaluation pipeline.
    return {
        "task_id": task_id,
        "verdict": "pass",
        "tokens_consumed": 0,
    }


@activity.defn
async def check_budget() -> dict[str, Any]:
    """Check whether the project budget has been exhausted.

    Returns:
        A dictionary with ``"exhausted"`` (bool), ``"consumed_pct"`` (float),
        and ``"remaining_tokens"`` (int).
    """
    activity.heartbeat("checking budget")
    logger.info("Checking budget")

    # Placeholder: in production, this queries the budget service.
    return {
        "exhausted": False,
        "consumed_pct": 0.0,
        "remaining_tokens": 10_000_000,
    }
