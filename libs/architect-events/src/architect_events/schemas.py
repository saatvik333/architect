"""Pydantic event models for the ARCHITECT event bus."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import (
    AgentType,
    ApprovalGateStatus,
    EnforcementLevel,
    EscalationCategory,
    EscalationSeverity,
    EvalVerdict,
    EventType,
    ModelTier,
    TaskType,
)
from architect_common.types import (
    AgentId,
    ApprovalGateId,
    ArchitectBase,
    EscalationId,
    EventId,
    HeuristicId,
    KnowledgeId,
    LedgerVersion,
    PatternId,
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


# ── Knowledge & Memory events ─────────────────────────────────────
class KnowledgeAcquiredEvent(ArchitectBase):
    """Emitted when new knowledge is acquired (docs, examples, patterns)."""

    knowledge_id: KnowledgeId
    topic: str
    source: str  # "doc_fetch" | "example_mine" | "task_completion"


class PatternExtractedEvent(ArchitectBase):
    """Emitted when observations are compressed into a reusable pattern."""

    pattern_id: PatternId
    pattern_type: str
    source_count: int


class HeuristicCreatedEvent(ArchitectBase):
    """Emitted when patterns are synthesized into a heuristic rule."""

    heuristic_id: HeuristicId
    domain: str
    condition: str
    action: str


class CompressionCompletedEvent(ArchitectBase):
    """Emitted when a compression pipeline run finishes."""

    patterns_created: int
    heuristics_created: int
    strategies_proposed: int


# ── Economic Governor events ──────────────────────────────────────
class BudgetThresholdAlertEvent(ArchitectBase):
    """Emitted when budget crosses a threshold."""

    level: EnforcementLevel
    consumed_pct: float
    consumed_tokens: int
    remaining_tokens: int
    burn_rate_tokens_per_min: float


class BudgetTierDowngradeEvent(ArchitectBase):
    """Emitted when the Governor forces routing to a cheaper tier."""

    previous_max_tier: ModelTier
    enforced_max_tier: ModelTier
    reason: str


class BudgetTaskPausedEvent(ArchitectBase):
    """Emitted when a task is paused due to budget pressure."""

    task_id: TaskId
    reason: str


class BudgetHaltEvent(ArchitectBase):
    """Emitted when budget is exhausted and all work halts."""

    consumed_pct: float
    tasks_cancelled: int
    progress_report: dict[str, object] = Field(default_factory=dict)


class SpinDetectedEvent(ArchitectBase):
    """Emitted when an agent is detected spinning without progress."""

    agent_id: AgentId
    task_id: TaskId
    retry_count: int
    tokens_wasted: int


class EfficiencyUpdatedEvent(ArchitectBase):
    """Emitted when agent efficiency scores are recalculated."""

    agent_id: AgentId
    efficiency_score: float
    tasks_completed: int
    quality_score: float
    tokens_consumed: int


# ── Human Interface events ────────────────────────────────────────
class EscalationCreatedEvent(ArchitectBase):
    """Emitted when a new escalation is raised."""

    escalation_id: EscalationId
    category: EscalationCategory
    severity: EscalationSeverity
    summary: str
    source_agent_id: AgentId | None = None
    source_task_id: TaskId | None = None


class EscalationResolvedEvent(ArchitectBase):
    """Emitted when an escalation is resolved."""

    escalation_id: EscalationId
    resolved_by: str
    resolution: str


class ApprovalRequestedEvent(ArchitectBase):
    """Emitted when an approval gate is created."""

    gate_id: ApprovalGateId
    action_type: str
    resource_id: str | None = None
    required_approvals: int


class ApprovalResolvedEvent(ArchitectBase):
    """Emitted when an approval gate is resolved."""

    gate_id: ApprovalGateId
    status: ApprovalGateStatus
