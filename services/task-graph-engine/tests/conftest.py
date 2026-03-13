"""Shared fixtures for Task Graph Engine tests."""

from __future__ import annotations

import pytest

from architect_common.enums import AgentType, ModelTier, StatusEnum, TaskType
from architect_common.types import TaskId, new_task_id
from task_graph_engine.graph import TaskDAG
from task_graph_engine.models import Task, TaskBudget


@pytest.fixture
def task_factory():
    """Factory fixture that creates Task instances with sensible defaults."""

    def _make(
        *,
        task_id: TaskId | None = None,
        task_type: TaskType = TaskType.IMPLEMENT_FEATURE,
        agent_type: AgentType = AgentType.CODER,
        model_tier: ModelTier = ModelTier.TIER_2,
        priority: int = 5,
        status: StatusEnum = StatusEnum.PENDING,
        dependencies: list[TaskId] | None = None,
        description: str = "test task",
        max_retries: int = 3,
    ) -> Task:
        return Task(
            id=task_id or new_task_id(),
            type=task_type,
            agent_type=agent_type,
            model_tier=model_tier,
            priority=priority,
            status=status,
            dependencies=dependencies or [],
            description=description,
            budget=TaskBudget(max_retries=max_retries),
        )

    return _make


@pytest.fixture
def empty_dag() -> TaskDAG:
    """Return a fresh, empty TaskDAG."""
    return TaskDAG()


@pytest.fixture
def linear_dag(task_factory, empty_dag):
    """Build a simple linear DAG: A -> B -> C."""
    a = task_factory(description="task A", priority=3)
    b = task_factory(description="task B", priority=2, dependencies=[a.id])
    c = task_factory(description="task C", priority=1, dependencies=[b.id])

    dag = empty_dag
    dag.add_task(a)
    dag.add_task(b)
    dag.add_task(c)
    dag.add_dependency(a.id, b.id)
    dag.add_dependency(b.id, c.id)

    return dag, a, b, c


@pytest.fixture
def diamond_dag(task_factory, empty_dag):
    """Build a diamond DAG: A -> B, A -> C, B -> D, C -> D."""
    a = task_factory(description="task A", priority=4)
    b = task_factory(description="task B", priority=3, dependencies=[a.id])
    c = task_factory(description="task C", priority=2, dependencies=[a.id])
    d = task_factory(
        description="task D",
        priority=1,
        dependencies=[b.id, c.id],
    )

    dag = empty_dag
    dag.add_task(a)
    dag.add_task(b)
    dag.add_task(c)
    dag.add_task(d)
    dag.add_dependency(a.id, b.id)
    dag.add_dependency(a.id, c.id)
    dag.add_dependency(b.id, d.id)
    dag.add_dependency(c.id, d.id)

    return dag, a, b, c, d
