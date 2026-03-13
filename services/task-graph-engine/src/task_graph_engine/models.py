"""Pydantic domain models for the Task Graph Engine."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import Field

from architect_common.enums import (
    AgentType,
    EvalVerdict,
    ModelTier,
    StatusEnum,
    TaskType,
)
from architect_common.types import (
    AgentId,
    ArchitectBase,
    TaskId,
    new_task_id,
    utcnow,
)


class TaskBudget(ArchitectBase):
    """Resource budget assigned to a single task."""

    max_tokens: int = Field(default=100_000, ge=0)
    max_time: timedelta = Field(default_factory=lambda: timedelta(minutes=30))
    max_retries: int = Field(default=3, ge=0, le=10)
    max_output_size_bytes: int = Field(default=1_000_000, ge=0)


class TaskInput(ArchitectBase):
    """An input artifact required by a task."""

    key: str
    artifact_uri: str = ""
    content_hash: str = ""


class TaskOutput(ArchitectBase):
    """An output artifact produced by a task."""

    key: str
    artifact_uri: str = ""
    content_hash: str = ""
    size_bytes: int = Field(default=0, ge=0)


class TaskRetryRecord(ArchitectBase):
    """Record of a single task execution attempt."""

    attempt: int = Field(ge=1)
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    verdict: EvalVerdict | None = None
    failure_reason: str | None = None
    tokens_consumed: int = Field(default=0, ge=0)


class TaskTimestamps(ArchitectBase):
    """Lifecycle timestamps for a task."""

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Task(ArchitectBase):
    """A single unit of work in the task graph."""

    id: TaskId = Field(default_factory=new_task_id)
    type: TaskType = TaskType.IMPLEMENT_FEATURE
    agent_type: AgentType = AgentType.CODER
    model_tier: ModelTier = ModelTier.TIER_2

    dependencies: list[TaskId] = Field(default_factory=list)
    dependents: list[TaskId] = Field(default_factory=list)

    inputs: list[TaskInput] = Field(default_factory=list)
    outputs: list[TaskOutput] = Field(default_factory=list)

    budget: TaskBudget = Field(default_factory=TaskBudget)
    status: StatusEnum = StatusEnum.PENDING
    assigned_agent: AgentId | None = None
    priority: int = Field(default=0, ge=0)

    timestamps: TaskTimestamps = Field(default_factory=TaskTimestamps)
    current_attempt: int = Field(default=0, ge=0)
    retry_history: list[TaskRetryRecord] = Field(default_factory=list)

    verdict: EvalVerdict | None = None
    error_message: str | None = None

    # Optional human-readable description carried through decomposition.
    description: str = ""


class TaskGraph(ArchitectBase):
    """Snapshot of a fully decomposed task graph."""

    tasks: list[Task] = Field(default_factory=list)
    execution_order: list[TaskId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
