"""FastAPI route definitions for the Evaluation Engine."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from architect_common.enums import EvalVerdict, HealthStatus
from architect_common.types import TaskId
from evaluation_engine.api.dependencies import get_evaluator
from evaluation_engine.evaluator import Evaluator

router = APIRouter()

_SERVICE_STARTED_AT = time.monotonic()

# ── In-memory report store (production would use a database) ──────────
_report_store: dict[str, dict[str, Any]] = {}


# ── Request / Response schemas ────────────────────────────────────────


class EvaluateRequest(BaseModel):
    """Request body for POST /evaluate."""

    task_id: str = Field(description="Branded task identifier.")
    sandbox_session_id: str = Field(description="Active sandbox session to evaluate.")


class EvaluateResponse(BaseModel):
    """Response body for POST /evaluate."""

    task_id: str
    overall_verdict: EvalVerdict
    layers_evaluated: int
    report: dict[str, Any]


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "evaluation-engine"
    status: HealthStatus
    uptime_seconds: float = 0.0


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/evaluate", response_model=EvaluateResponse)
async def run_evaluation(
    body: EvaluateRequest,
    evaluator: Evaluator = Depends(get_evaluator),
) -> EvaluateResponse:
    """Run the full evaluation pipeline for a task."""
    report = await evaluator.evaluate(
        task_id=TaskId(body.task_id),
        sandbox_session_id=body.sandbox_session_id,
    )

    report_dict = report.model_dump(mode="json")
    _report_store[body.task_id] = report_dict

    return EvaluateResponse(
        task_id=body.task_id,
        overall_verdict=report.overall_verdict,
        layers_evaluated=len(report.layers),
        report=report_dict,
    )


@router.get("/reports/{task_id}")
async def get_report(task_id: str) -> dict[str, Any]:
    """Retrieve a previously generated evaluation report by task ID."""
    report = _report_store.get(task_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No evaluation report found for task_id={task_id}",
        )
    return report


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        uptime_seconds=round(time.monotonic() - _SERVICE_STARTED_AT, 1),
    )
