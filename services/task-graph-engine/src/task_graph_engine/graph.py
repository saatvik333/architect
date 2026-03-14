"""DAG-based task graph using networkx."""

from __future__ import annotations

from typing import cast

import networkx as nx

from architect_common.errors import CircularDependencyError, TaskNotFoundError
from architect_common.types import TaskId
from task_graph_engine.models import Task, TaskGraph


class TaskDAG:
    """Directed Acyclic Graph of tasks backed by :mod:`networkx`.

    Each node in the graph stores a full :class:`Task` instance under the
    ``"task"`` attribute.  Edges represent dependency relationships where
    ``(A, B)`` means *A must finish before B can start*.
    """

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    # ── Mutation ────────────────────────────────────────────────────

    def add_task(self, task: Task) -> None:
        """Add a task as a node in the DAG.

        Raises:
            ValueError: If a task with the same ID already exists.
        """
        if task.id in self._graph:
            msg = f"Task {task.id} already exists in the graph"
            raise ValueError(msg)
        self._graph.add_node(task.id, task=task)

    def add_dependency(self, from_task: TaskId, to_task: TaskId) -> None:
        """Declare that *from_task* must complete before *to_task* can start.

        Creates a directed edge ``from_task -> to_task``.

        Raises:
            TaskNotFoundError: If either task ID is not in the graph.
        """
        if from_task not in self._graph:
            raise TaskNotFoundError(
                f"Dependency source task {from_task} not found",
                details={"task_id": from_task},
            )
        if to_task not in self._graph:
            raise TaskNotFoundError(
                f"Dependency target task {to_task} not found",
                details={"task_id": to_task},
            )
        self._graph.add_edge(from_task, to_task)

    # ── Queries ────────────────────────────────────────────────────

    def get_task(self, task_id: TaskId) -> Task:
        """Return the :class:`Task` for the given ID.

        Raises:
            TaskNotFoundError: If the task is not in the graph.
        """
        if task_id not in self._graph:
            raise TaskNotFoundError(
                f"Task {task_id} not found",
                details={"task_id": task_id},
            )
        return cast(Task, self._graph.nodes[task_id]["task"])

    @property
    def task_ids(self) -> list[TaskId]:
        """Return all task IDs currently in the graph."""
        return list(self._graph.nodes)

    @property
    def task_count(self) -> int:
        """Return the number of tasks in the graph."""
        return int(self._graph.number_of_nodes())

    def get_execution_order(self) -> list[TaskId]:
        """Return a topological ordering of all tasks.

        Raises:
            CircularDependencyError: If the graph contains a cycle.
        """
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible as exc:
            cycle = nx.find_cycle(self._graph)
            raise CircularDependencyError(
                "Task graph contains a cycle",
                details={"cycle": [f"{u}->{v}" for u, v in cycle]},
            ) from exc

    def get_ready_tasks(self, completed: set[TaskId]) -> list[TaskId]:
        """Return task IDs whose dependencies are all in *completed*.

        Only tasks that have not themselves been completed are returned.

        Args:
            completed: Set of task IDs that have already finished.

        Returns:
            List of task IDs that are ready to execute, ordered by the
            priority stored on each :class:`Task` (descending).
        """
        ready: list[TaskId] = []
        for node in self._graph.nodes:
            if node in completed:
                continue
            predecessors = set(self._graph.predecessors(node))
            if predecessors <= completed:
                ready.append(node)

        # Sort by priority descending so the scheduler picks the most
        # important tasks first.
        ready.sort(
            key=lambda tid: self._graph.nodes[tid]["task"].priority,
            reverse=True,
        )
        return ready

    def get_dependents(self, task_id: TaskId) -> list[TaskId]:
        """Return direct dependents (successors) of a task."""
        if task_id not in self._graph:
            raise TaskNotFoundError(
                f"Task {task_id} not found",
                details={"task_id": task_id},
            )
        return list(self._graph.successors(task_id))

    def get_dependencies(self, task_id: TaskId) -> list[TaskId]:
        """Return direct dependencies (predecessors) of a task."""
        if task_id not in self._graph:
            raise TaskNotFoundError(
                f"Task {task_id} not found",
                details={"task_id": task_id},
            )
        return list(self._graph.predecessors(task_id))

    # ── Validation ─────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Check the graph for structural problems.

        Returns:
            A list of human-readable error strings.  An empty list means the
            graph is valid.
        """
        errors: list[str] = []

        # Check for cycles.
        if not nx.is_directed_acyclic_graph(self._graph):
            try:
                cycle = nx.find_cycle(self._graph)
                cycle_str = " -> ".join(f"{u}" for u, _ in cycle)
                errors.append(f"Cycle detected: {cycle_str}")
            except nx.NetworkXNoCycle:
                pass  # Shouldn't happen if is_dag returned False, but be safe.

        # Check for dangling dependency references.
        for node in self._graph.nodes:
            task: Task = self._graph.nodes[node]["task"]
            for dep_id in task.dependencies:
                if dep_id not in self._graph:
                    errors.append(f"Task {task.id} references missing dependency {dep_id}")

        # Check for isolated nodes with no edges (warning, not error).
        if self._graph.number_of_nodes() > 1:
            for node in nx.isolates(self._graph):
                errors.append(f"Task {node} is isolated (no dependencies or dependents)")

        return errors

    # ── Export ──────────────────────────────────────────────────────

    def to_task_graph(self) -> TaskGraph:
        """Serialize the DAG into a :class:`TaskGraph` snapshot.

        Raises:
            CircularDependencyError: If the graph contains a cycle.
        """
        execution_order = self.get_execution_order()
        tasks = [self._graph.nodes[tid]["task"] for tid in execution_order]
        return TaskGraph(tasks=tasks, execution_order=execution_order)
