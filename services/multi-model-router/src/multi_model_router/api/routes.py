"""FastAPI route definitions for the Multi-Model Router."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus
from multi_model_router.cost_collector import CostCollector
from multi_model_router.models import (
    CostSummary,
    RouteRequest,
    RouteResponse,
    RoutingStats,
)
from multi_model_router.router import Router
from multi_model_router.scorer import ComplexityScorer

from .dependencies import get_cost_collector, get_router, get_scorer

router = APIRouter()

_SERVICE_STARTED_AT = time.monotonic()


# ── Request / Response schemas ─────────────────────────────────────


class RouteRequestWithTokens(RouteRequest, frozen=True):
    """Extended route request that accepts optional token counts for cost tracking."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "multi-model-router"
    status: HealthStatus
    uptime_seconds: float = 0.0


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/api/v1/route", response_model=RouteResponse)
async def route_task(
    body: RouteRequestWithTokens,
    scorer: ComplexityScorer = Depends(get_scorer),
    task_router: Router = Depends(get_router),
    cost_collector: CostCollector = Depends(get_cost_collector),
) -> RouteResponse:
    """Score task complexity and route to the appropriate model tier."""
    complexity = scorer.score(
        task_type=body.task_type,
        description=body.description,
        token_estimate=body.token_estimate,
        keywords=body.keywords,
    )

    decision = task_router.route(
        task_id=body.task_id,
        task_type=body.task_type,
        complexity=complexity,
    )

    # Record cost if token counts provided
    if body.input_tokens > 0 or body.output_tokens > 0:
        cost_collector.record_routing(
            decision=decision,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
        )
    else:
        # Still record routing for stats (zero tokens)
        cost_collector.record_routing(
            decision=decision,
            input_tokens=0,
            output_tokens=0,
        )

    return RouteResponse(decision=decision)


@router.get("/api/v1/route/costs", response_model=CostSummary)
async def get_costs(
    cost_collector: CostCollector = Depends(get_cost_collector),
) -> CostSummary:
    """Return aggregated cost information across all tiers."""
    return cost_collector.get_cost_summary()


@router.get("/api/v1/route/stats", response_model=RoutingStats)
async def get_stats(
    cost_collector: CostCollector = Depends(get_cost_collector),
) -> RoutingStats:
    """Return aggregate routing statistics."""
    return cost_collector.get_stats()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        uptime_seconds=round(time.monotonic() - _SERVICE_STARTED_AT, 1),
    )
