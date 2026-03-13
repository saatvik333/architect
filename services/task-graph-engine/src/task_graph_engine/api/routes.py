"""FastAPI routes for the Task Graph Engine API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus, StatusEnum, TaskType
from architect_common.errors import TaskNotFoundError
from architect_common.types import TaskId
from task_graph_engine.api.dependencies import (
    get_config,
    get_decomposer,
    get_task_dag,
)
from task_graph_engine.config import TaskGraphEngineConfig
from task_graph_engine.decomposer import TaskDecomposer
from task_graph_engine.graph import TaskDAG
from task_graph_engine.models import Task

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────


class SubmitSpecRequest(BaseModel):
    """Request body for submitting a project spec for decomposition."""

    spec: dict[str, Any]
    use_llm: bool = False


class SubmitSpecResponse(BaseModel):
    """Response after successful spec decomposition."""

    task_count: int
    task_ids: list[str]
    execution_order: list[str]
    validation_errors: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    """Serialized task for API responses."""

    id: str
    type: str
    agent_type: str
    model_tier: str
    status: str
    priority: int
    description: str
    dependencies: list[str]
    dependents: list[str]
    assigned_agent: str | None = None
    current_attempt: int = 0
    verdict: str | None = None
    error_message: str | None = None


class TaskListResponse(BaseModel):
    """Paginated list of tasks."""

    tasks: list[TaskResponse]
    total: int


class GraphResponse(BaseModel):
    """Current state of the task graph."""

    task_count: int
    tasks: list[TaskResponse]
    execution_order: list[str]
    validation_errors: list[str]


class HealthResponse(BaseModel):
    """Service health check response."""

    status: str
    service: str = "task-graph-engine"
    version: str = "0.1.0"
    details: dict[str, Any] = Field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────


def _task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        type=task.type.value,
        agent_type=task.agent_type.value,
        model_tier=task.model_tier.value,
        status=task.status.value,
        priority=task.priority,
        description=task.description,
        dependencies=list(task.dependencies),
        dependents=list(task.dependents),
        assigned_agent=task.assigned_agent,
        current_attempt=task.current_attempt,
        verdict=task.verdict.value if task.verdict else None,
        error_message=task.error_message,
    )


# ── Routes ────────────────────────────────────────────────────────


@router.post(
    "/tasks/submit",
    response_model=SubmitSpecResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_spec(
    body: SubmitSpecRequest,
    decomposer: Annotated[TaskDecomposer, Depends(get_decomposer)],
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
) -> SubmitSpecResponse:
    """Submit a project specification for decomposition and scheduling.

    The spec is decomposed into tasks, which are added to the in-memory
    DAG with dependency edges.  Returns the task IDs and execution order.
    """
    spec = body.spec
    if body.use_llm:
        spec["use_llm"] = True

    tasks = await decomposer.decompose_spec(spec)

    # Add tasks to the DAG.
    for task in tasks:
        dag.add_task(task)

    # Wire dependency edges.
    for task in tasks:
        for dep_id in task.dependencies:
            dag.add_dependency(dep_id, task.id)

    # Validate and get execution order.
    validation_errors = dag.validate()
    execution_order = dag.get_execution_order()

    return SubmitSpecResponse(
        task_count=len(tasks),
        task_ids=[t.id for t in tasks],
        execution_order=execution_order,
        validation_errors=validation_errors,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
) -> TaskResponse:
    """Get details of a specific task by ID."""
    try:
        task = dag.get_task(TaskId(task_id))
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        ) from exc
    return _task_to_response(task)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
    task_status: Annotated[StatusEnum | None, Query(alias="status")] = None,
    task_type: Annotated[TaskType | None, Query(alias="type")] = None,
) -> TaskListResponse:
    """List all tasks in the graph, optionally filtered by status or type."""
    all_ids = dag.task_ids
    tasks: list[Task] = []

    for tid in all_ids:
        task = dag.get_task(tid)
        if task_status is not None and task.status != task_status:
            continue
        if task_type is not None and task.type != task_type:
            continue
        tasks.append(task)

    responses = [_task_to_response(t) for t in tasks]
    return TaskListResponse(tasks=responses, total=len(responses))


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
) -> GraphResponse:
    """Get the current state of the full task graph."""
    validation_errors = dag.validate()

    all_ids = dag.task_ids
    tasks = [_task_to_response(dag.get_task(tid)) for tid in all_ids]

    try:
        execution_order = dag.get_execution_order()
    except Exception:
        execution_order = []

    return GraphResponse(
        task_count=len(tasks),
        tasks=tasks,
        execution_order=execution_order,
        validation_errors=validation_errors,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check(
    config: Annotated[TaskGraphEngineConfig, Depends(get_config)],
    dag: Annotated[TaskDAG, Depends(get_task_dag)],
) -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status=HealthStatus.HEALTHY.value,
        details={
            "task_count": dag.task_count,
            "environment": config.log_level,
        },
    )
