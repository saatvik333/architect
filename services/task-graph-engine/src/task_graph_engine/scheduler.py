"""Task scheduler: picks the next ready task and manages lifecycle transitions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from architect_common.enums import EvalVerdict, EventType, StatusEnum
from architect_common.errors import InvalidTransitionError
from architect_common.logging import get_logger
from architect_common.types import AgentId, TaskId, utcnow
from task_graph_engine.graph import TaskDAG
from task_graph_engine.models import Task, TaskRetryRecord, TaskTimestamps

if TYPE_CHECKING:
    from architect_db.repositories.task_repo import TaskRepository
    from architect_events.publisher import EventPublisher

logger = get_logger(component="task_scheduler")

# Valid status transitions.
_VALID_TRANSITIONS: dict[StatusEnum, set[StatusEnum]] = {
    StatusEnum.PENDING: {StatusEnum.RUNNING, StatusEnum.CANCELLED, StatusEnum.BLOCKED},
    StatusEnum.BLOCKED: {StatusEnum.PENDING, StatusEnum.CANCELLED},
    StatusEnum.RUNNING: {StatusEnum.COMPLETED, StatusEnum.FAILED, StatusEnum.CANCELLED},
    StatusEnum.FAILED: {StatusEnum.PENDING, StatusEnum.CANCELLED},  # retry -> pending
    StatusEnum.COMPLETED: set(),
    StatusEnum.CANCELLED: set(),
}


class TaskScheduler:
    """Coordinates task scheduling and lifecycle management.

    Works with a :class:`TaskDAG` for dependency-aware scheduling,
    a :class:`TaskRepository` for persistence, and an
    :class:`EventPublisher` for lifecycle event emission.
    """

    def __init__(
        self,
        task_repo: TaskRepository,
        event_publisher: EventPublisher,
        dag: TaskDAG | None = None,
    ) -> None:
        self._task_repo = task_repo
        self._event_publisher = event_publisher
        self._dag = dag or TaskDAG()
        self._completed: set[TaskId] = set()
        self._schedule_lock = asyncio.Lock()

    @property
    def dag(self) -> TaskDAG:
        """The underlying task DAG."""
        return self._dag

    @property
    def completed(self) -> set[TaskId]:
        """Set of completed task IDs."""
        return self._completed

    # ── Scheduling ─────────────────────────────────────────────────

    async def schedule_next(self) -> Task | None:
        """Return the highest-priority task that is ready to run.

        A task is "ready" when all of its dependencies are in the
        *completed* set.  Among ready tasks, the one with the highest
        priority is returned.

        Returns:
            The next :class:`Task` to execute, or ``None`` if nothing is ready.
        """
        ready_ids = self._dag.get_ready_tasks(self._completed)
        if not ready_ids:
            logger.debug("No ready tasks")
            return None

        # Return the highest-priority ready task (already sorted by get_ready_tasks).
        task = self._dag.get_task(ready_ids[0])
        logger.info("Scheduled next task", task_id=task.id, task_type=task.type)
        return task

    async def schedule_and_claim(self, agent_id: AgentId) -> Task | None:
        """Atomically schedule the next ready task and mark it as running.

        Acquires a lock so that two agents cannot claim the same task
        concurrently.

        Args:
            agent_id: The agent that will execute the claimed task.

        Returns:
            The claimed :class:`Task` (now in RUNNING status), or ``None``
            if no task is ready.
        """
        async with self._schedule_lock:
            task = await self.schedule_next()
            if task is None:
                return None
            await self.mark_running(task.id, agent_id)
            return self._dag.get_task(task.id)

    # ── Lifecycle transitions ──────────────────────────────────────

    async def mark_running(self, task_id: TaskId, agent_id: AgentId) -> None:
        """Transition a task to RUNNING and assign it to an agent.

        Args:
            task_id: The task to start.
            agent_id: The agent that will execute the task.

        Raises:
            TaskNotFoundError: If the task is not in the DAG.
            InvalidTransitionError: If the task is not in PENDING status.
        """
        task = self._dag.get_task(task_id)
        self._assert_transition(task, StatusEnum.RUNNING)

        now = utcnow()
        updated = task.model_copy(
            update={
                "status": StatusEnum.RUNNING,
                "assigned_agent": agent_id,
                "current_attempt": task.current_attempt + 1,
                "timestamps": task.timestamps.model_copy(update={"started_at": now}),
            }
        )
        self._dag.update_task(task_id, updated)

        await self._task_repo.update_status(task_id, StatusEnum.RUNNING)
        await self._publish_event(
            EventType.TASK_STARTED,
            {
                "task_id": task_id,
                "agent_id": agent_id,
            },
        )
        logger.info("Task marked running", task_id=task_id, agent_id=agent_id)

    async def mark_completed(self, task_id: TaskId, verdict: EvalVerdict) -> None:
        """Transition a task to COMPLETED with an evaluation verdict.

        Args:
            task_id: The task that finished.
            verdict: The evaluation result.

        Raises:
            TaskNotFoundError: If the task is not in the DAG.
            InvalidTransitionError: If the task is not in RUNNING status.
        """
        task = self._dag.get_task(task_id)
        self._assert_transition(task, StatusEnum.COMPLETED)

        now = utcnow()
        updated = task.model_copy(
            update={
                "status": StatusEnum.COMPLETED,
                "verdict": verdict,
                "timestamps": task.timestamps.model_copy(update={"completed_at": now}),
            }
        )
        self._dag.update_task(task_id, updated)
        self._completed.add(task_id)

        await self._task_repo.update_status(task_id, StatusEnum.COMPLETED)
        await self._publish_event(
            EventType.TASK_COMPLETED,
            {
                "task_id": task_id,
                "verdict": verdict.value,
            },
        )
        logger.info("Task completed", task_id=task_id, verdict=verdict)

    async def mark_failed(self, task_id: TaskId, error: str) -> None:
        """Transition a task to FAILED with an error message.

        Args:
            task_id: The task that failed.
            error: A description of what went wrong.

        Raises:
            TaskNotFoundError: If the task is not in the DAG.
            InvalidTransitionError: If the task is not in RUNNING status.
        """
        task = self._dag.get_task(task_id)
        self._assert_transition(task, StatusEnum.FAILED)

        now = utcnow()
        retry_record = TaskRetryRecord(
            attempt=task.current_attempt,
            started_at=task.timestamps.started_at or now,
            ended_at=now,
            verdict=EvalVerdict.FAIL_SOFT,
            failure_reason=error,
        )
        updated = task.model_copy(
            update={
                "status": StatusEnum.FAILED,
                "error_message": error,
                "timestamps": task.timestamps.model_copy(update={"completed_at": now}),
                "retry_history": [*task.retry_history, retry_record],
            }
        )
        self._dag.update_task(task_id, updated)

        await self._task_repo.update_status(task_id, StatusEnum.FAILED, error_message=error)
        await self._publish_event(
            EventType.TASK_FAILED,
            {
                "task_id": task_id,
                "error_message": error,
            },
        )
        logger.warning("Task failed", task_id=task_id, error=error)

    async def should_retry(self, task_id: TaskId) -> bool:
        """Determine whether a failed task should be retried.

        A task is eligible for retry if:
        - It is in FAILED status.
        - Its current attempt count is less than its budget's max_retries.

        If eligible, the task is transitioned back to PENDING.

        Args:
            task_id: The task to check.

        Returns:
            ``True`` if the task was reset to PENDING for retry.
        """
        task = self._dag.get_task(task_id)

        if task.status != StatusEnum.FAILED:
            return False

        if task.current_attempt >= task.budget.max_retries:
            logger.info(
                "Task exhausted retries",
                task_id=task_id,
                attempts=task.current_attempt,
                max_retries=task.budget.max_retries,
            )
            return False

        # Reset to PENDING for retry.
        updated = task.model_copy(
            update={
                "status": StatusEnum.PENDING,
                "error_message": None,
                "assigned_agent": None,
                "timestamps": TaskTimestamps(
                    created_at=task.timestamps.created_at,
                ),
            }
        )
        self._dag.update_task(task_id, updated)

        await self._task_repo.update_status(task_id, StatusEnum.PENDING)
        await self._publish_event(
            EventType.TASK_RETRIED,
            {
                "task_id": task_id,
                "attempt": task.current_attempt + 1,
            },
        )
        logger.info("Task queued for retry", task_id=task_id, attempt=task.current_attempt + 1)
        return True

    # ── Helpers ─────────────────────────────────────────────────────

    def _assert_transition(self, task: Task, target: StatusEnum) -> None:
        """Raise if transitioning from *task.status* to *target* is invalid."""
        allowed = _VALID_TRANSITIONS.get(task.status, set())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition task {task.id} from {task.status} to {target}",
                details={
                    "task_id": task.id,
                    "current_status": task.status.value,
                    "target_status": target.value,
                },
            )

    async def _publish_event(self, event_type: EventType, payload: dict[str, object]) -> None:
        """Publish a lifecycle event to the event bus."""
        from architect_events.schemas import EventEnvelope

        event = EventEnvelope(type=event_type, payload=payload)
        try:
            await self._event_publisher.publish(event)
        except Exception:
            # Log but do not crash the scheduler if event publishing fails.
            logger.exception("Failed to publish event", event_type=event_type)
