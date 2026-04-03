"""Pydantic event models for the ARCHITECT event bus."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import (
    AgentType,
    ApprovalGateStatus,
    DeploymentStage,
    EnforcementLevel,
    EscalationCategory,
    EscalationSeverity,
    EvalVerdict,
    EventType,
    FailureCode,
    FindingSeverity,
    ImprovementType,
    ModelTier,
    RollbackReason,
    ScanType,
    ScanVerdict,
    TaskType,
)
from architect_common.types import (
    AgentId,
    ApprovalGateId,
    ArchitectBase,
    DeploymentId,
    EscalationId,
    EventId,
    FailureRecordId,
    HeuristicId,
    ImprovementId,
    KnowledgeId,
    LedgerVersion,
    PatternId,
    PostMortemId,
    ProposalId,
    SecurityScanId,
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


class TaskCompletedPayload(ArchitectBase):
    """Canonical payload for TASK_COMPLETED events.

    Covers the superset of fields needed by all consumers. Uses relaxed
    string types so it can be ``model_validate``-d directly from a raw
    event payload dict.
    """

    task_id: str = ""
    agent_id: str = ""
    verdict: str = ""
    quality_score: float = Field(default=1.0)
    tokens_consumed: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)


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


# ── Security Immune events ───────────────────────────────────────
class SecurityScanStartedEvent(ArchitectBase):
    """Emitted when a security scan begins."""

    scan_id: SecurityScanId
    scan_type: ScanType
    target: str


class SecurityScanCompletedEvent(ArchitectBase):
    """Emitted when a security scan finishes."""

    scan_id: SecurityScanId
    scan_type: ScanType
    verdict: ScanVerdict
    findings_count: int
    critical_count: int


class SecurityFindingCreatedEvent(ArchitectBase):
    """Emitted when a high/critical finding is discovered."""

    finding_id: str
    scan_id: SecurityScanId
    severity: FindingSeverity
    category: str
    description: str


class SecurityPolicyViolationEvent(ArchitectBase):
    """Emitted when a security policy rule is triggered."""

    policy_id: str
    scan_id: SecurityScanId
    action_taken: str
    details: dict[str, object] = Field(default_factory=dict)


class SecurityGateBlockedEvent(ArchitectBase):
    """Emitted when code is blocked by the security gate."""

    scan_id: SecurityScanId
    blocking_findings: int
    target: str


# ── Deployment Pipeline events ───────────────────────────────────
class DeploymentStartedEvent(ArchitectBase):
    """Emitted when a deployment workflow begins."""

    deployment_id: DeploymentId
    task_id: TaskId
    artifact_ref: str


class DeploymentStageChangedEvent(ArchitectBase):
    """Emitted at each traffic percentage change."""

    deployment_id: DeploymentId
    stage: DeploymentStage
    traffic_pct: int


class DeploymentCompletedEvent(ArchitectBase):
    """Emitted on successful full rollout."""

    deployment_id: DeploymentId
    task_id: TaskId
    duration_seconds: float


class DeploymentRolledBackEvent(ArchitectBase):
    """Emitted on rollback."""

    deployment_id: DeploymentId
    reason: RollbackReason
    stage_at_rollback: DeploymentStage


# ── Failure Taxonomy events ──────────────────────────────────────
class FailureClassifiedEvent(ArchitectBase):
    """Emitted when a failure is classified."""

    failure_record_id: FailureRecordId
    task_id: TaskId
    failure_code: FailureCode
    confidence: float


class ImprovementProposedEvent(ArchitectBase):
    """Emitted when improvements are generated from analysis."""

    improvement_id: ImprovementId
    improvement_type: ImprovementType
    description: str


class PostMortemCompletedEvent(ArchitectBase):
    """Emitted when post-mortem analysis finishes."""

    post_mortem_id: PostMortemId
    project_id: str
    failure_count: int
    improvements_proposed: int
