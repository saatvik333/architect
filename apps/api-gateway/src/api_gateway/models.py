"""API Gateway — request/response models."""

from __future__ import annotations

from pydantic import Field

from architect_common.types import AgentId, ArchitectBase, TaskId


class TaskSubmitRequest(ArchitectBase):
    """Task submission payload."""

    name: str
    description: str
    spec: dict  # type: ignore[type-arg]
    priority: int = 5
    parent_task_id: TaskId | None = None


class TaskSubmitResponse(ArchitectBase):
    """Response after submitting a task."""

    task_id: TaskId
    status: str


class TaskStatusResponse(ArchitectBase):
    """Full task status."""

    task_id: TaskId
    name: str
    status: str
    progress: float = 0.0
    children: list[TaskId] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class TaskLogEntry(ArchitectBase):
    """Single log entry."""

    timestamp: str
    level: str
    message: str
    source: str = ""


class TaskLogsResponse(ArchitectBase):
    """Log entries for a task."""

    task_id: TaskId
    entries: list[TaskLogEntry] = Field(default_factory=list)


class ProposalResponse(ArchitectBase):
    """Summary of a proposal."""

    proposal_id: str
    task_id: TaskId
    agent_id: AgentId
    mutations: list[dict] = Field(default_factory=list)  # type: ignore[type-arg]
    verdict: str = "pending"
    created_at: str = ""


class HealthResponse(ArchitectBase):
    """Aggregate health check response."""

    status: str
    services: dict[str, str] = Field(default_factory=dict)
    version: str = "0.1.0"


class WorldStateResponse(ArchitectBase):
    """Current world state snapshot."""

    version: int = 0
    data: dict = Field(default_factory=dict)  # type: ignore[type-arg]


class ProposalSubmitRequest(ArchitectBase):
    """Raw proposal submission."""

    task_id: TaskId
    agent_id: AgentId
    mutations: list[dict]  # type: ignore[type-arg]


class CancelRequest(ArchitectBase):
    """Task cancellation request."""

    force: bool = False
