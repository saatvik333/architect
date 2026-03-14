"""Domain models for the Multi-Model Router."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import ModelTier, TaskType
from architect_common.types import ArchitectBase, TaskId, utcnow


class ComplexityScore(ArchitectBase):
    """Computed complexity assessment for a task."""

    score: float = Field(ge=0.0, le=1.0)
    factors: dict[str, float] = Field(default_factory=dict)
    recommended_tier: ModelTier = ModelTier.TIER_2


class RoutingDecision(ArchitectBase):
    """The result of routing a task to a specific model tier."""

    task_id: TaskId
    selected_tier: ModelTier
    model_id: str
    complexity: ComplexityScore
    override_reason: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class EscalationRecord(ArchitectBase):
    """Tracks failure-based escalation state for a task."""

    task_id: TaskId
    failure_count: int = 0
    current_tier: ModelTier = ModelTier.TIER_3
    escalation_history: list[dict[str, str]] = Field(default_factory=list)
    needs_human: bool = False


class RoutingStats(ArchitectBase):
    """Aggregate routing statistics."""

    total_requests: int = 0
    tier_distribution: dict[str, int] = Field(default_factory=dict)
    escalation_count: int = 0
    average_complexity: float = 0.0


class RouteRequest(ArchitectBase):
    """Request body for POST /api/v1/route."""

    task_id: TaskId
    task_type: TaskType
    description: str = ""
    token_estimate: int = 0
    keywords: list[str] = Field(default_factory=list)


class RouteResponse(ArchitectBase):
    """Response body for POST /api/v1/route."""

    decision: RoutingDecision
