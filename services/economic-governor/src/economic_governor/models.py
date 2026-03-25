"""Domain models for the Economic Governor."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import BudgetPhase, EnforcementLevel
from architect_common.types import AgentId, ArchitectBase, TaskId, utcnow

# ── Budget models ────────────────────────────────────────────────


class PhaseAllocation(ArchitectBase):
    """Budget allocation for a single development phase."""

    phase: BudgetPhase
    allocated_tokens: int = 0
    allocated_pct: float = 0.0


class ProjectBudget(ArchitectBase):
    """Total project budget including per-phase allocations."""

    total_tokens: int
    total_usd: float
    phase_allocations: list[PhaseAllocation] = Field(default_factory=list)


class PhaseStatus(ArchitectBase):
    """Current consumption status for a single development phase."""

    phase: BudgetPhase
    allocated_tokens: int = 0
    allocated_pct: float = 0.0
    consumed_tokens: int = 0
    consumed_pct: float = 0.0


class BudgetSnapshot(ArchitectBase):
    """Point-in-time snapshot of overall budget state."""

    allocated_tokens: int = 0
    consumed_tokens: int = 0
    consumed_pct: float = 0.0
    consumed_usd: float = 0.0
    burn_rate_tokens_per_min: float = 0.0
    enforcement_level: EnforcementLevel = EnforcementLevel.NONE
    phase_breakdown: list[PhaseStatus] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


# ── Efficiency models ────────────────────────────────────────────


class AgentEfficiencyScore(ArchitectBase):
    """Efficiency score for a single agent."""

    agent_id: AgentId
    efficiency_score: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    quality_score: float = 0.0
    tokens_consumed: int = 0
    cost_usd: float = 0.0
    rank: int = 0


class EfficiencyLeaderboard(ArchitectBase):
    """Ranked list of agent efficiency scores."""

    entries: list[AgentEfficiencyScore] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=utcnow)


# ── Enforcement models ───────────────────────────────────────────


class EnforcementRecord(ArchitectBase):
    """Record of an enforcement action taken by the Governor."""

    id: str
    level: EnforcementLevel
    action_type: str
    target_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)
    budget_consumed_pct: float = 0.0
    timestamp: datetime = Field(default_factory=utcnow)


# ── Spin detection models ────────────────────────────────────────


class SpinDetection(ArchitectBase):
    """Result of spin detection analysis for an agent/task pair."""

    agent_id: AgentId
    task_id: TaskId
    is_spinning: bool = False
    retry_count: int = 0
    tokens_since_last_diff: int = 0


# ── Budget allocation request/result ─────────────────────────────


class BudgetAllocationRequest(ArchitectBase):
    """Request to allocate a budget for a project."""

    project_id: str
    estimated_complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    priority: int = Field(default=1, ge=1, le=5)
    deadline_hours: float | None = None


class BudgetAllocationResult(ArchitectBase):
    """Result of a budget allocation computation."""

    project_id: str
    total_tokens: int
    total_usd: float
    phase_allocations: list[PhaseAllocation] = Field(default_factory=list)
