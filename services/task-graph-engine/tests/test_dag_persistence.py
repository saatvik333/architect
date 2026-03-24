"""Tests for TaskDAG persistence and reconstruction."""

from __future__ import annotations

from unittest.mock import AsyncMock

from architect_common.enums import (
    AgentType,
    ModelTier,
    StatusEnum,
    TaskType,
)
from architect_common.types import TaskId
from task_graph_engine.graph import TaskDAG
from task_graph_engine.models import Task
from task_graph_engine.scheduler import TaskScheduler

# ── Helpers ────────────────────────────────────────────────────────


def _make_task(
    task_id: str,
    status: StatusEnum = StatusEnum.PENDING,
    deps: list[str] | None = None,
    priority: int = 5,
) -> Task:
    return Task(
        id=TaskId(task_id),
        type=TaskType.IMPLEMENT_FEATURE,
        status=status,
        priority=priority,
        dependencies=[TaskId(d) for d in deps] if deps else [],
    )


# ── TaskDAG.from_tasks tests ──────────────────────────────────────


class TestDAGReconstruction:
    """Tests for TaskDAG.from_tasks class method."""

    def test_from_tasks_empty(self) -> None:
        dag = TaskDAG.from_tasks([])
        assert dag.task_count == 0

    def test_from_tasks_single(self) -> None:
        tasks = [_make_task("t-1")]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.task_count == 1
        assert dag.get_task(TaskId("t-1")).id == TaskId("t-1")

    def test_from_tasks_with_dependencies(self) -> None:
        tasks = [
            _make_task("t-1"),
            _make_task("t-2", deps=["t-1"]),
            _make_task("t-3", deps=["t-1", "t-2"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.task_count == 3

        # t-1 should be ready (no deps).
        ready = dag.get_ready_tasks(set())
        assert TaskId("t-1") in ready
        # t-2 and t-3 should not be ready.
        assert TaskId("t-2") not in ready
        assert TaskId("t-3") not in ready

    def test_from_tasks_completed_excluded_from_ready(self) -> None:
        tasks = [
            _make_task("t-1", status=StatusEnum.COMPLETED),
            _make_task("t-2", deps=["t-1"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        completed = {TaskId("t-1")}
        ready = dag.get_ready_tasks(completed)
        assert TaskId("t-2") in ready

    def test_from_tasks_ignores_missing_deps(self) -> None:
        """Dependencies referencing non-existent tasks are silently skipped."""
        tasks = [_make_task("t-1", deps=["t-nonexistent"])]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.task_count == 1
        # The task should be ready since its only dep is missing (edge not created).
        ready = dag.get_ready_tasks(set())
        assert TaskId("t-1") in ready

    def test_from_tasks_preserves_priority_ordering(self) -> None:
        tasks = [
            _make_task("t-low", priority=1),
            _make_task("t-high", priority=10),
            _make_task("t-mid", priority=5),
        ]
        dag = TaskDAG.from_tasks(tasks)
        ready = dag.get_ready_tasks(set())
        assert ready[0] == TaskId("t-high")
        assert ready[-1] == TaskId("t-low")

    def test_from_tasks_execution_order_is_valid(self) -> None:
        tasks = [
            _make_task("t-1"),
            _make_task("t-2", deps=["t-1"]),
            _make_task("t-3", deps=["t-2"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        order = dag.get_execution_order()
        assert order.index(TaskId("t-1")) < order.index(TaskId("t-2"))
        assert order.index(TaskId("t-2")) < order.index(TaskId("t-3"))

    def test_from_tasks_diamond(self) -> None:
        tasks = [
            _make_task("t-a"),
            _make_task("t-b", deps=["t-a"]),
            _make_task("t-c", deps=["t-a"]),
            _make_task("t-d", deps=["t-b", "t-c"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.task_count == 4

        # After a completes, b and c are ready.
        ready = dag.get_ready_tasks({TaskId("t-a")})
        assert set(ready) == {TaskId("t-b"), TaskId("t-c")}

        # d needs both b and c.
        ready = dag.get_ready_tasks({TaskId("t-a"), TaskId("t-b")})
        assert TaskId("t-d") not in ready

        ready = dag.get_ready_tasks({TaskId("t-a"), TaskId("t-b"), TaskId("t-c")})
        assert TaskId("t-d") in ready

    def test_from_tasks_get_dependents(self) -> None:
        tasks = [
            _make_task("t-1"),
            _make_task("t-2", deps=["t-1"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.get_dependents(TaskId("t-1")) == [TaskId("t-2")]
        assert dag.get_dependents(TaskId("t-2")) == []

    def test_from_tasks_get_dependencies(self) -> None:
        tasks = [
            _make_task("t-1"),
            _make_task("t-2", deps=["t-1"]),
        ]
        dag = TaskDAG.from_tasks(tasks)
        assert dag.get_dependencies(TaskId("t-1")) == []
        assert dag.get_dependencies(TaskId("t-2")) == [TaskId("t-1")]


# ── TaskScheduler.load_from_db tests ──────────────────────────────


def _make_orm_row(
    task_id: str,
    status: str = "pending",
    priority: int = 5,
    deps: list[str] | None = None,
) -> object:
    """Create a lightweight mock that mimics an ORM Task row."""
    from datetime import UTC, datetime

    row = AsyncMock()
    row.id = task_id
    row.type = TaskType.IMPLEMENT_FEATURE
    row.agent_type = AgentType.CODER
    row.model_tier = ModelTier.TIER_2
    row.status = StatusEnum(status)
    row.priority = priority
    row.dependencies = deps
    row.dependents = None
    row.budget = None
    row.assigned_agent = None
    row.current_attempt = 0
    row.created_at = datetime.now(UTC)
    row.started_at = None
    row.completed_at = None
    row.verdict = None
    row.error_message = None
    return row


class TestSchedulerLoadFromDB:
    """Tests for TaskScheduler.load_from_db."""

    async def test_load_empty_db(self) -> None:
        repo = AsyncMock()
        repo.list_all = AsyncMock(return_value=[])
        publisher = AsyncMock()

        scheduler = TaskScheduler(task_repo=repo, event_publisher=publisher)
        count = await scheduler.load_from_db()

        assert count == 0
        assert scheduler.dag.task_count == 0
        assert scheduler.completed == set()

    async def test_load_single_task(self) -> None:
        row = _make_orm_row("t-1")
        repo = AsyncMock()
        repo.list_all = AsyncMock(return_value=[row])
        publisher = AsyncMock()

        scheduler = TaskScheduler(task_repo=repo, event_publisher=publisher)
        count = await scheduler.load_from_db()

        assert count == 1
        assert scheduler.dag.task_count == 1
        task = scheduler.dag.get_task(TaskId("t-1"))
        assert task.status == StatusEnum.PENDING

    async def test_load_with_dependencies(self) -> None:
        rows = [
            _make_orm_row("t-1"),
            _make_orm_row("t-2", deps=["t-1"]),
            _make_orm_row("t-3", deps=["t-1", "t-2"]),
        ]
        repo = AsyncMock()
        repo.list_all = AsyncMock(return_value=rows)
        publisher = AsyncMock()

        scheduler = TaskScheduler(task_repo=repo, event_publisher=publisher)
        count = await scheduler.load_from_db()

        assert count == 3
        ready = scheduler.dag.get_ready_tasks(scheduler.completed)
        assert TaskId("t-1") in ready
        assert TaskId("t-2") not in ready

    async def test_load_rebuilds_completed_set(self) -> None:
        rows = [
            _make_orm_row("t-1", status="completed"),
            _make_orm_row("t-2", status="completed"),
            _make_orm_row("t-3", deps=["t-1", "t-2"]),
        ]
        repo = AsyncMock()
        repo.list_all = AsyncMock(return_value=rows)
        publisher = AsyncMock()

        scheduler = TaskScheduler(task_repo=repo, event_publisher=publisher)
        count = await scheduler.load_from_db()

        assert count == 3
        assert TaskId("t-1") in scheduler.completed
        assert TaskId("t-2") in scheduler.completed
        assert TaskId("t-3") not in scheduler.completed

        # t-3 should now be ready.
        ready = scheduler.dag.get_ready_tasks(scheduler.completed)
        assert TaskId("t-3") in ready

    async def test_load_syncs_distributed_lock(self) -> None:
        rows = [
            _make_orm_row("t-1", status="completed"),
        ]
        repo = AsyncMock()
        repo.list_all = AsyncMock(return_value=rows)
        publisher = AsyncMock()
        lock = AsyncMock()

        scheduler = TaskScheduler(
            task_repo=repo,
            event_publisher=publisher,
            distributed_lock=lock,
        )
        count = await scheduler.load_from_db()

        assert count == 1
        lock.mark_completed.assert_called_once_with("t-1")

    async def test_load_paginates_large_result_sets(self) -> None:
        """Verify that load_from_db paginates when the repo returns full batches."""
        batch_1 = [_make_orm_row(f"t-{i}") for i in range(1000)]
        batch_2 = [_make_orm_row(f"t-{i}") for i in range(1000, 1500)]
        repo = AsyncMock()
        repo.list_all = AsyncMock(side_effect=[batch_1, batch_2])
        publisher = AsyncMock()

        scheduler = TaskScheduler(task_repo=repo, event_publisher=publisher)
        count = await scheduler.load_from_db()

        assert count == 1500
        assert scheduler.dag.task_count == 1500
        assert repo.list_all.call_count == 2
