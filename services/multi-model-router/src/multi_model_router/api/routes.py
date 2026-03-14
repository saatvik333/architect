"""FastAPI route definitions for the Multi-Model Router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from architect_common.enums import HealthStatus
from multi_model_router.models import RouteRequest, RouteResponse, RoutingStats
from multi_model_router.router import Router
from multi_model_router.scorer import ComplexityScorer

from .dependencies import get_router, get_scorer

router = APIRouter()

# ── In-memory stats tracking ────────────────────────────────────────
_stats: dict[str, Any] = {
    "total_requests": 0,
    "tier_distribution": {},
    "escalation_count": 0,
    "complexity_sum": 0.0,
}


# ── Response schemas ────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "multi-model-router"
    status: HealthStatus


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/api/v1/route", response_model=RouteResponse)
async def route_task(
    body: RouteRequest,
    scorer: ComplexityScorer = Depends(get_scorer),
    task_router: Router = Depends(get_router),
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

    # Update stats
    _stats["total_requests"] += 1
    _stats["complexity_sum"] += complexity.score
    tier_key = decision.selected_tier.value
    _stats["tier_distribution"][tier_key] = _stats["tier_distribution"].get(tier_key, 0) + 1

    return RouteResponse(decision=decision)


@router.get("/api/v1/route/stats", response_model=RoutingStats)
async def get_stats() -> RoutingStats:
    """Return aggregate routing statistics."""
    total = _stats["total_requests"]
    avg = _stats["complexity_sum"] / total if total > 0 else 0.0

    return RoutingStats(
        total_requests=total,
        tier_distribution=dict(_stats["tier_distribution"]),
        escalation_count=_stats["escalation_count"],
        average_complexity=round(avg, 4),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)
