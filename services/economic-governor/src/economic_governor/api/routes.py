"""FastAPI route definitions for the Economic Governor."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from architect_common.enums import EnforcementLevel, HealthStatus
from architect_common.types import AgentId
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer
from economic_governor.models import (
    AgentEfficiencyScore,
    BudgetAllocationRequest,
    BudgetAllocationResult,
    BudgetSnapshot,
    EnforcementRecord,
    PhaseStatus,
)

from .dependencies import get_budget_tracker, get_efficiency_scorer, get_enforcer

router = APIRouter()

_SERVICE_STARTED_AT = time.monotonic()


# ── Request / Response schemas ────────────────────────────────────


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "economic-governor"
    status: HealthStatus
    uptime_seconds: float = 0.0


class RecordConsumptionRequest(BaseModel):
    """Request body for POST /api/v1/budget/record-consumption."""

    agent_id: str
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)


class RecordConsumptionResponse(BaseModel):
    """Response body for POST /api/v1/budget/record-consumption."""

    enforcement_level: EnforcementLevel


class EnforcementLevelResponse(BaseModel):
    """Response body for GET /api/v1/enforcement/current-level."""

    level: EnforcementLevel
    consumed_pct: float


class LeaderboardResponse(BaseModel):
    """Response body for GET /api/v1/efficiency/leaderboard."""

    entries: list[AgentEfficiencyScore]
    computed_at: str


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/api/v1/budget/status", response_model=BudgetSnapshot)
async def get_budget_status(
    tracker: BudgetTracker = Depends(get_budget_tracker),
) -> BudgetSnapshot:
    """Return the current budget snapshot."""
    return tracker.get_snapshot()


@router.get("/api/v1/budget/phases", response_model=list[PhaseStatus])
async def get_budget_phases(
    tracker: BudgetTracker = Depends(get_budget_tracker),
) -> list[PhaseStatus]:
    """Return per-phase budget breakdown."""
    return tracker.get_snapshot().phase_breakdown


@router.post("/api/v1/budget/allocate", response_model=BudgetAllocationResult)
async def allocate_budget(
    body: BudgetAllocationRequest,
    tracker: BudgetTracker = Depends(get_budget_tracker),
) -> BudgetAllocationResult:
    """Compute a budget allocation for a project."""
    return tracker.allocate_project_budget(body)


@router.post("/api/v1/budget/record-consumption", response_model=RecordConsumptionResponse)
async def record_consumption(
    body: RecordConsumptionRequest,
    tracker: BudgetTracker = Depends(get_budget_tracker),
) -> RecordConsumptionResponse:
    """Record token consumption and return the current enforcement level."""
    level = tracker.record_consumption(
        agent_id=body.agent_id,
        tokens=body.tokens,
        cost_usd=body.cost_usd,
    )
    return RecordConsumptionResponse(enforcement_level=level)


@router.get("/api/v1/efficiency/leaderboard")
async def get_leaderboard(
    scorer: EfficiencyScorer = Depends(get_efficiency_scorer),
) -> LeaderboardResponse:
    """Return the agent efficiency leaderboard."""
    board = scorer.compute_scores()
    return LeaderboardResponse(
        entries=board.entries,
        computed_at=board.computed_at.isoformat(),
    )


@router.get("/api/v1/efficiency/agent/{agent_id}", response_model=AgentEfficiencyScore)
async def get_agent_efficiency(
    agent_id: str,
    scorer: EfficiencyScorer = Depends(get_efficiency_scorer),
) -> AgentEfficiencyScore:
    """Return efficiency score for a specific agent."""
    return scorer.get_agent_score(AgentId(agent_id))


@router.get("/api/v1/enforcement/history", response_model=list[EnforcementRecord])
async def get_enforcement_history(
    enforcer: Enforcer = Depends(get_enforcer),
) -> list[EnforcementRecord]:
    """Return the enforcement action history."""
    return enforcer.get_history()


@router.get("/api/v1/enforcement/current-level", response_model=EnforcementLevelResponse)
async def get_current_enforcement_level(
    tracker: BudgetTracker = Depends(get_budget_tracker),
) -> EnforcementLevelResponse:
    """Return the current enforcement level."""
    snapshot = tracker.get_snapshot()
    return EnforcementLevelResponse(
        level=snapshot.enforcement_level,
        consumed_pct=snapshot.consumed_pct,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        uptime_seconds=round(time.monotonic() - _SERVICE_STARTED_AT, 1),
    )
