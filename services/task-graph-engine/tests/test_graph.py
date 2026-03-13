"""Tests for DAG operations, topological sort, and cycle detection."""

from __future__ import annotations

import pytest

from architect_common.errors import CircularDependencyError, TaskNotFoundError
from architect_common.types import TaskId


class TestAddTask:
    """Tests for TaskDAG.add_task."""

    def test_add_single_task(self, empty_dag, task_factory):
        task = task_factory()
        empty_dag.add_task(task)
        assert empty_dag.task_count == 1
        assert task.id in empty_dag.task_ids

    def test_add_multiple_tasks(self, empty_dag, task_factory):
        t1 = task_factory(description="first")
        t2 = task_factory(description="second")
        empty_dag.add_task(t1)
        empty_dag.add_task(t2)
        assert empty_dag.task_count == 2

    def test_add_duplicate_task_raises(self, empty_dag, task_factory):
        task = task_factory()
        empty_dag.add_task(task)
        with pytest.raises(ValueError, match="already exists"):
            empty_dag.add_task(task)

    def test_get_task(self, empty_dag, task_factory):
        task = task_factory(description="findme")
        empty_dag.add_task(task)
        found = empty_dag.get_task(task.id)
        assert found.id == task.id
        assert found.description == "findme"

    def test_get_task_not_found(self, empty_dag):
        with pytest.raises(TaskNotFoundError):
            empty_dag.get_task(TaskId("task-nonexistent"))


class TestAddDependency:
    """Tests for TaskDAG.add_dependency."""

    def test_add_valid_dependency(self, empty_dag, task_factory):
        a = task_factory(description="A")
        b = task_factory(description="B")
        empty_dag.add_task(a)
        empty_dag.add_task(b)
        empty_dag.add_dependency(a.id, b.id)

        deps = empty_dag.get_dependencies(b.id)
        assert a.id in deps

    def test_add_dependency_missing_source(self, empty_dag, task_factory):
        b = task_factory()
        empty_dag.add_task(b)
        with pytest.raises(TaskNotFoundError, match="source"):
            empty_dag.add_dependency(TaskId("task-ghost"), b.id)

    def test_add_dependency_missing_target(self, empty_dag, task_factory):
        a = task_factory()
        empty_dag.add_task(a)
        with pytest.raises(TaskNotFoundError, match="target"):
            empty_dag.add_dependency(a.id, TaskId("task-ghost"))


class TestExecutionOrder:
    """Tests for topological sort."""

    def test_linear_order(self, linear_dag):
        dag, a, b, c = linear_dag
        order = dag.get_execution_order()
        assert order.index(a.id) < order.index(b.id)
        assert order.index(b.id) < order.index(c.id)

    def test_diamond_order(self, diamond_dag):
        dag, a, b, c, d = diamond_dag
        order = dag.get_execution_order()
        # A must come before B and C, both before D.
        assert order.index(a.id) < order.index(b.id)
        assert order.index(a.id) < order.index(c.id)
        assert order.index(b.id) < order.index(d.id)
        assert order.index(c.id) < order.index(d.id)

    def test_single_task_order(self, empty_dag, task_factory):
        t = task_factory()
        empty_dag.add_task(t)
        order = empty_dag.get_execution_order()
        assert order == [t.id]

    def test_empty_dag_order(self, empty_dag):
        order = empty_dag.get_execution_order()
        assert order == []


class TestCycleDetection:
    """Tests for cycle detection via validate() and get_execution_order()."""

    def test_cycle_raises_on_execution_order(self, empty_dag, task_factory):
        a = task_factory(description="A")
        b = task_factory(description="B")
        empty_dag.add_task(a)
        empty_dag.add_task(b)
        empty_dag.add_dependency(a.id, b.id)
        empty_dag.add_dependency(b.id, a.id)

        with pytest.raises(CircularDependencyError, match="cycle"):
            empty_dag.get_execution_order()

    def test_validate_detects_cycle(self, empty_dag, task_factory):
        a = task_factory(description="A")
        b = task_factory(description="B")
        c = task_factory(description="C")
        empty_dag.add_task(a)
        empty_dag.add_task(b)
        empty_dag.add_task(c)
        empty_dag.add_dependency(a.id, b.id)
        empty_dag.add_dependency(b.id, c.id)
        empty_dag.add_dependency(c.id, a.id)

        errors = empty_dag.validate()
        assert any("Cycle" in e for e in errors)

    def test_validate_no_errors_on_valid_dag(self, linear_dag):
        dag, _, _, _ = linear_dag
        errors = dag.validate()
        # Filter out isolation warnings (only relevant for multi-node graphs).
        structural_errors = [e for e in errors if "Cycle" in e or "missing" in e]
        assert structural_errors == []


class TestGetReadyTasks:
    """Tests for dependency-aware ready-task queries."""

    def test_no_deps_means_ready(self, empty_dag, task_factory):
        t = task_factory(priority=5)
        empty_dag.add_task(t)
        ready = empty_dag.get_ready_tasks(completed=set())
        assert ready == [t.id]

    def test_linear_initial_ready(self, linear_dag):
        dag, a, b, c = linear_dag
        ready = dag.get_ready_tasks(completed=set())
        assert ready == [a.id]

    def test_linear_after_first_complete(self, linear_dag):
        dag, a, b, c = linear_dag
        ready = dag.get_ready_tasks(completed={a.id})
        assert ready == [b.id]

    def test_linear_after_two_complete(self, linear_dag):
        dag, a, b, c = linear_dag
        ready = dag.get_ready_tasks(completed={a.id, b.id})
        assert ready == [c.id]

    def test_linear_all_complete(self, linear_dag):
        dag, a, b, c = linear_dag
        ready = dag.get_ready_tasks(completed={a.id, b.id, c.id})
        assert ready == []

    def test_diamond_parallel(self, diamond_dag):
        dag, a, b, c, d = diamond_dag
        # After A completes, both B and C become ready.
        ready = dag.get_ready_tasks(completed={a.id})
        assert set(ready) == {b.id, c.id}

    def test_diamond_d_needs_both(self, diamond_dag):
        dag, a, b, c, d = diamond_dag
        # Only B done — D still blocked on C.
        ready = dag.get_ready_tasks(completed={a.id, b.id})
        assert d.id not in ready
        assert c.id in ready

    def test_diamond_d_ready_when_both_done(self, diamond_dag):
        dag, a, b, c, d = diamond_dag
        ready = dag.get_ready_tasks(completed={a.id, b.id, c.id})
        assert ready == [d.id]

    def test_ready_tasks_sorted_by_priority(self, empty_dag, task_factory):
        low = task_factory(priority=1)
        high = task_factory(priority=10)
        mid = task_factory(priority=5)
        empty_dag.add_task(low)
        empty_dag.add_task(high)
        empty_dag.add_task(mid)

        ready = empty_dag.get_ready_tasks(completed=set())
        assert ready[0] == high.id
        assert ready[-1] == low.id


class TestGetDependentsAndDependencies:
    """Tests for graph traversal helpers."""

    def test_get_dependents(self, linear_dag):
        dag, a, b, c = linear_dag
        assert dag.get_dependents(a.id) == [b.id]
        assert dag.get_dependents(b.id) == [c.id]
        assert dag.get_dependents(c.id) == []

    def test_get_dependencies(self, linear_dag):
        dag, a, b, c = linear_dag
        assert dag.get_dependencies(a.id) == []
        assert dag.get_dependencies(b.id) == [a.id]
        assert dag.get_dependencies(c.id) == [b.id]

    def test_get_dependents_not_found(self, empty_dag):
        with pytest.raises(TaskNotFoundError):
            empty_dag.get_dependents(TaskId("task-nonexistent"))

    def test_get_dependencies_not_found(self, empty_dag):
        with pytest.raises(TaskNotFoundError):
            empty_dag.get_dependencies(TaskId("task-nonexistent"))


class TestToTaskGraph:
    """Tests for serialization to TaskGraph."""

    def test_to_task_graph(self, linear_dag):
        dag, a, b, c = linear_dag
        tg = dag.to_task_graph()
        assert len(tg.tasks) == 3
        assert len(tg.execution_order) == 3
        assert tg.execution_order.index(a.id) < tg.execution_order.index(b.id)
        assert tg.execution_order.index(b.id) < tg.execution_order.index(c.id)

    def test_to_task_graph_empty(self, empty_dag):
        tg = empty_dag.to_task_graph()
        assert tg.tasks == []
        assert tg.execution_order == []

    def test_to_task_graph_with_cycle_raises(self, empty_dag, task_factory):
        a = task_factory()
        b = task_factory()
        empty_dag.add_task(a)
        empty_dag.add_task(b)
        empty_dag.add_dependency(a.id, b.id)
        empty_dag.add_dependency(b.id, a.id)

        with pytest.raises(CircularDependencyError):
            empty_dag.to_task_graph()


class TestValidate:
    """Tests for graph validation."""

    def test_valid_dag_no_errors(self, diamond_dag):
        dag, *_ = diamond_dag
        errors = dag.validate()
        cycle_errors = [e for e in errors if "Cycle" in e or "missing" in e]
        assert cycle_errors == []

    def test_missing_dependency_reference(self, empty_dag, task_factory):
        ghost_id = TaskId("task-doesnotexist")
        task = task_factory(dependencies=[ghost_id])
        empty_dag.add_task(task)
        errors = empty_dag.validate()
        assert any("missing dependency" in e for e in errors)
