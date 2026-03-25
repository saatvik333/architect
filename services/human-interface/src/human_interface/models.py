"""Domain models for the Human Interface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from architect_common.enums import (
    ApprovalGateStatus,
    EscalationCategory,
    EscalationSeverity,
    EscalationStatus,
)
from architect_common.types import (
    AgentId,
    ApprovalGateId,
    ArchitectBase,
    EscalationId,
    TaskId,
    utcnow,
)

# ── Escalation models ───────────────────────────────────────────────


class EscalationOption(ArchitectBase):
    """A single option the human may choose when resolving an escalation."""

    label: str
    description: str
    tradeoff: str = ""


class EscalationDecision(ArchitectBase):
    """Input to the should_escalate() function."""

    confidence: float = Field(ge=0.0, le=1.0)
    is_security_critical: bool = False
    cost_impact: float | None = None
    is_architectural_fork: bool = False


class CreateEscalationRequest(BaseModel):
    """Request body for creating a new escalation."""

    source_agent_id: AgentId | None = None
    source_task_id: TaskId | None = None
    correlation_id: str | None = None
    summary: str
    category: EscalationCategory
    severity: EscalationSeverity
    options: list[EscalationOption] = Field(default_factory=list)
    recommended_option: str | None = None
    reasoning: str | None = None
    risk_if_wrong: str | None = None
    decision_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_security_critical: bool = False
    cost_impact_pct: float | None = Field(default=None, ge=0.0)
    expires_in_minutes: int | None = None


class ResolveEscalationRequest(BaseModel):
    """Request body for resolving an escalation."""

    resolved_by: str
    resolution: str
    custom_input: dict[str, Any] | None = None


class EscalationResponse(ArchitectBase):
    """API response for a single escalation."""

    id: EscalationId
    source_agent_id: AgentId | None = None
    source_task_id: TaskId | None = None
    summary: str
    category: EscalationCategory
    severity: EscalationSeverity
    options: list[EscalationOption] = Field(default_factory=list)
    recommended_option: str | None = None
    reasoning: str | None = None
    risk_if_wrong: str | None = None
    status: EscalationStatus = EscalationStatus.PENDING
    resolved_by: str | None = None
    resolution: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    resolved_at: datetime | None = None


class EscalationStatsResponse(ArchitectBase):
    """Aggregated statistics for escalations."""

    total: int = 0
    pending: int = 0
    resolved: int = 0
    expired: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)


# ── Approval gate models ────────────────────────────────────────────


class CreateApprovalGateRequest(BaseModel):
    """Request body for creating a new approval gate."""

    action_type: str
    resource_id: str | None = None
    required_approvals: int = Field(default=1, ge=1)
    context: dict[str, Any] | None = None
    expires_in_minutes: int | None = None


class VoteRequest(BaseModel):
    """Request body for casting a vote on an approval gate."""

    voter: str
    decision: Literal["approve", "deny"]
    comment: str | None = None


class ApprovalGateResponse(ArchitectBase):
    """API response for a single approval gate."""

    id: ApprovalGateId
    action_type: str
    resource_id: str | None = None
    required_approvals: int = 1
    current_approvals: int = 0
    status: ApprovalGateStatus = ApprovalGateStatus.PENDING
    context: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    resolved_at: datetime | None = None


# ── Progress / Activity models ──────────────────────────────────────


class ActivityEvent(ArchitectBase):
    """A single event in the activity feed."""

    id: str
    type: str
    timestamp: datetime = Field(default_factory=utcnow)
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ProgressSummary(ArchitectBase):
    """Aggregated project progress for the dashboard."""

    project_name: str = "ARCHITECT"
    status: str = "running"
    completion_pct: float = 0.0
    tasks_completed: int = 0
    tasks_total: int = 0
    budget_consumed_pct: float = 0.0
    tests_passing: int = 0
    tests_failing: int = 0
    coverage_pct: float = 0.0
    blockers: list[str] = Field(default_factory=list)
    recent_events: list[ActivityEvent] = Field(default_factory=list)


# ── WebSocket models ────────────────────────────────────────────────


class WebSocketMessage(ArchitectBase):
    """Message sent over WebSocket to connected dashboard clients."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


__all__ = [
    "ActivityEvent",
    "ApprovalGateResponse",
    "CreateApprovalGateRequest",
    "CreateEscalationRequest",
    "EscalationDecision",
    "EscalationOption",
    "EscalationResponse",
    "EscalationStatsResponse",
    "ProgressSummary",
    "ResolveEscalationRequest",
    "VoteRequest",
    "WebSocketMessage",
]
