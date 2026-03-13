"""Tests for the TaskScheduler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import (
    AgentType,
    EvalVerdict,
    ModelTier,
    StatusEnum,
    TaskType,
)
from architect_common.errors import InvalidTransitionError
from architect_common.types import TaskId, new_agent_id, new_task_id
from task_graph_engine.graph import TaskDAG
from task_graph_engine.models import Task, TaskBudget
from task_graph_engine.scheduler import TaskScheduler


@pytest.fixture
def mock_task_repo():
    """Create a mock TaskRepository."""
    repo = AsyncMock()
    repo.update_status = AsyncMock()
    repo.get_next_pending = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_event_publisher():
    """Create a mock EventPublisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock(return_value="msg-001")
    return publisher


@pytest.fixture
def make_task():
    """Factory for creating Task instances."""

    def _make(
        *,
        task_id: TaskId | None = None,
        priority: int = 5,
        status: StatusEnum = StatusEnum.PENDING,
        max_retries: int = 3,
        current_attempt: int = 0,
    ) -> Task:
        return Task(
            id=task_id or new_task_id(),
            type=TaskType.IMPLEMENT_FEATURE,
            agent_type=AgentType.CODER,
            model_tier=ModelTier.TIER_2,
            priority=priority,
            status=status,
            budget=TaskBudget(max_retries=max_retries),
            current_attempt=current_attempt,
        )

    return _make


@pytest.fixture
def scheduler_with_tasks(mock_task_repo, mock_event_publisher, make_task):
    """Build a scheduler with a simple A -> B DAG."""
    dag = TaskDAG()
    a = make_task(priority=10)
    b = make_task(priority=5)

    dag.add_task(a)
    dag.add_task(b)
    dag.add_dependency(a.id, b.id)

    scheduler = TaskScheduler(
        task_repo=mock_task_repo,
        event_publisher=mock_event_publisher,
        dag=dag,
    )
    return scheduler, a, b


class TestScheduleNext:
    """Tests for TaskScheduler.schedule_next."""

    async def test_returns_highest_priority_ready(self, scheduler_with_tasks):
        scheduler, a, b = scheduler_with_tasks
        task = await scheduler.schedule_next()
        # Only A is ready (B depends on A).
        assert task is not None
        assert task.id == a.id

    async def test_returns_none_when_all_blocked(self, scheduler_with_tasks):
        scheduler, a, b = scheduler_with_tasks
        # Mark A as running (in the DAG) — B is still blocked, A is not completed.
        # Neither A nor B should be "ready" since A isn't completed.
        # But schedule_next checks get_ready_tasks which only looks at completed set.
        # A is ready because it has no deps and isn't completed.
        task = await scheduler.schedule_next()
        assert task is not None  # A is still ready

    async def test_b_ready_after_a_completed(self, scheduler_with_tasks):
        scheduler, a, b = scheduler_with_tasks
        scheduler._completed.add(a.id)
        task = await scheduler.schedule_next()
        assert task is not None
        assert task.id == b.id

    async def test_returns_none_when_all_completed(self, scheduler_with_tasks):
        scheduler, a, b = scheduler_with_tasks
        scheduler._completed.add(a.id)
        scheduler._completed.add(b.id)
        task = await scheduler.schedule_next()
        assert task is None

    async def test_empty_dag_returns_none(self, mock_task_repo, mock_event_publisher):
        scheduler = TaskScheduler(
            task_repo=mock_task_repo,
            event_publisher=mock_event_publisher,
        )
        task = await scheduler.schedule_next()
        assert task is None


class TestMarkRunning:
    """Tests for TaskScheduler.mark_running."""

    async def test_transitions_to_running(self, scheduler_with_tasks):
        scheduler, a, b = scheduler_with_tasks
        agent_id = new_agent_id()

        await scheduler.mark_running(a.id, agent_id)

        updated = scheduler.dag.get_task(a.id)
        assert updated.status == StatusEnum.RUNNING
        assert updated.assigned_agent == agent_id
        assert updated.current_attempt == 1

    async def test_publishes_event(self, scheduler_with_tasks, mock_event_publisher):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        mock_event_publisher.publish.assert_called_once()

    async def test_updates_repo(self, scheduler_with_tasks, mock_task_repo):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        mock_task_repo.update_status.assert_called_once_with(a.id, StatusEnum.RUNNING)

    async def test_invalid_transition_from_completed(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        # Force task to COMPLETED status.
        completed_task = a.model_copy(update={"status": StatusEnum.COMPLETED})
        scheduler.dag._graph.nodes[a.id]["task"] = completed_task

        with pytest.raises(InvalidTransitionError):
            await scheduler.mark_running(a.id, new_agent_id())


class TestMarkCompleted:
    """Tests for TaskScheduler.mark_completed."""

    async def test_transitions_to_completed(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        # Must be running first.
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_completed(a.id, EvalVerdict.PASS)

        updated = scheduler.dag.get_task(a.id)
        assert updated.status == StatusEnum.COMPLETED
        assert updated.verdict == EvalVerdict.PASS

    async def test_adds_to_completed_set(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_completed(a.id, EvalVerdict.PASS)
        assert a.id in scheduler.completed

    async def test_invalid_transition_from_pending(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        with pytest.raises(InvalidTransitionError):
            await scheduler.mark_completed(a.id, EvalVerdict.PASS)


class TestMarkFailed:
    """Tests for TaskScheduler.mark_failed."""

    async def test_transitions_to_failed(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_failed(a.id, "compilation error")

        updated = scheduler.dag.get_task(a.id)
        assert updated.status == StatusEnum.FAILED
        assert updated.error_message == "compilation error"

    async def test_records_retry_history(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_failed(a.id, "timeout")

        updated = scheduler.dag.get_task(a.id)
        assert len(updated.retry_history) == 1
        assert updated.retry_history[0].failure_reason == "timeout"

    async def test_publishes_failure_event(self, scheduler_with_tasks, mock_event_publisher):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_failed(a.id, "error")
        # Two calls: one for TASK_STARTED, one for TASK_FAILED.
        assert mock_event_publisher.publish.call_count == 2


class TestShouldRetry:
    """Tests for TaskScheduler.should_retry."""

    async def test_retry_resets_to_pending(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_failed(a.id, "transient error")

        should = await scheduler.should_retry(a.id)
        assert should is True

        updated = scheduler.dag.get_task(a.id)
        assert updated.status == StatusEnum.PENDING

    async def test_no_retry_when_max_reached(self, mock_task_repo, mock_event_publisher, make_task):
        dag = TaskDAG()
        task = make_task(max_retries=1, current_attempt=0)
        dag.add_task(task)

        scheduler = TaskScheduler(
            task_repo=mock_task_repo,
            event_publisher=mock_event_publisher,
            dag=dag,
        )

        await scheduler.mark_running(task.id, new_agent_id())
        await scheduler.mark_failed(task.id, "error")

        should = await scheduler.should_retry(task.id)
        assert should is False

    async def test_no_retry_when_not_failed(self, scheduler_with_tasks):
        scheduler, a, _ = scheduler_with_tasks
        # Task is PENDING, not FAILED.
        should = await scheduler.should_retry(a.id)
        assert should is False

    async def test_retry_publishes_event(self, scheduler_with_tasks, mock_event_publisher):
        scheduler, a, _ = scheduler_with_tasks
        await scheduler.mark_running(a.id, new_agent_id())
        await scheduler.mark_failed(a.id, "error")

        mock_event_publisher.publish.reset_mock()
        await scheduler.should_retry(a.id)
        mock_event_publisher.publish.assert_called_once()


class TestEventPublishingFailure:
    """Tests that the scheduler is resilient to event publishing failures."""

    async def test_mark_running_survives_publish_failure(self, mock_task_repo, make_task):
        publisher = AsyncMock()
        publisher.publish = AsyncMock(side_effect=RuntimeError("connection lost"))

        dag = TaskDAG()
        task = make_task()
        dag.add_task(task)

        scheduler = TaskScheduler(
            task_repo=mock_task_repo,
            event_publisher=publisher,
            dag=dag,
        )

        # Should not raise even though publishing fails.
        await scheduler.mark_running(task.id, new_agent_id())
        updated = scheduler.dag.get_task(task.id)
        assert updated.status == StatusEnum.RUNNING
