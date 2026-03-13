"""Pydantic event models for the ARCHITECT event bus."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import (
    AgentType,
    EvalVerdict,
    EventType,
    ModelTier,
    TaskType,
)
from architect_common.types import (
    AgentId,
    ArchitectBase,
    EventId,
    LedgerVersion,
    ProposalId,
    TaskId,
    new_event_id,
    utcnow,
)


# ── Envelope ────────────────────────────────────────────────────────
class EventEnvelope(ArchitectBase):
    """Top-level wrapper for every event published on the bus."""

    id: EventId = Field(default_factory=new_event_id)
    type: EventType
    timestamp: datetime = Field(default_factory=utcnow)
    correlation_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


# ── Task lifecycle events ───────────────────────────────────────────
class TaskCreatedEvent(ArchitectBase):
    """Emitted when a new task is added to the task graph."""

    task_id: TaskId
    task_type: TaskType
    agent_type: AgentType


class TaskStartedEvent(ArchitectBase):
    """Emitted when an agent picks up a task."""

    task_id: TaskId
    agent_id: AgentId


class TaskCompletedEvent(ArchitectBase):
    """Emitted when an agent successfully finishes a task."""

    task_id: TaskId
    agent_id: AgentId
    verdict: EvalVerdict


class TaskFailedEvent(ArchitectBase):
    """Emitted when a task fails."""

    task_id: TaskId
    agent_id: AgentId
    error_message: str


# ── Proposal lifecycle events ──────────────────────────────────────
class ProposalCreatedEvent(ArchitectBase):
    """Emitted when an agent submits a proposal."""

    proposal_id: ProposalId
    agent_id: AgentId
    task_id: TaskId


class ProposalAcceptedEvent(ArchitectBase):
    """Emitted when a proposal is accepted and merged into the ledger."""

    proposal_id: ProposalId
    ledger_version: LedgerVersion


class ProposalRejectedEvent(ArchitectBase):
    """Emitted when a proposal is rejected by the evaluation engine."""

    proposal_id: ProposalId
    reason: str


# ── Agent lifecycle events ─────────────────────────────────────────
class AgentSpawnedEvent(ArchitectBase):
    """Emitted when a new agent process is spawned."""

    agent_id: AgentId
    agent_type: AgentType
    model_tier: ModelTier
    task_id: TaskId


class AgentCompletedEvent(ArchitectBase):
    """Emitted when an agent finishes all work and shuts down."""

    agent_id: AgentId
    tokens_consumed: int


# ── Evaluation events ──────────────────────────────────────────────
class EvalCompletedEvent(ArchitectBase):
    """Emitted when the evaluation pipeline finishes for a task."""

    task_id: TaskId
    verdict: EvalVerdict
    layer_results: list[dict[str, object]] = Field(default_factory=list)


# ── Budget events ──────────────────────────────────────────────────
class BudgetWarningEvent(ArchitectBase):
    """Emitted when token consumption exceeds a warning threshold."""

    consumed_pct: float
    remaining_tokens: int
