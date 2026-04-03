"""FastAPI route definitions for the Deployment Pipeline."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from architect_common.enums import DeploymentStatus, HealthStatus
from architect_common.health import HealthResponse
from architect_common.types import DeploymentId, TaskId
from deployment_pipeline.models import DeploymentArtifact, DeploymentState
from deployment_pipeline.pipeline_manager import PipelineManager

from .dependencies import get_pipeline_manager

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────


class StartDeploymentRequest(BaseModel):
    """Request body for POST /api/v1/deployments."""

    task_id: str
    artifact_ref: str
    eval_report_summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StartDeploymentResponse(BaseModel):
    """Response body for POST /api/v1/deployments."""

    deployment_id: str
    status: DeploymentStatus


class RollbackRequest(BaseModel):
    """Request body for POST /api/v1/deployments/{id}/rollback."""

    reason: str = "manual"


class ActionResponse(BaseModel):
    """Generic response for action endpoints."""

    success: bool
    message: str = ""


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("/api/v1/deployments", response_model=StartDeploymentResponse, status_code=201)
async def start_deployment(
    body: StartDeploymentRequest,
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> StartDeploymentResponse:
    """Start a new deployment."""
    artifact = DeploymentArtifact(
        task_id=TaskId(body.task_id),
        artifact_ref=body.artifact_ref,
        eval_report_summary=body.eval_report_summary,
    )
    state = await manager.start_deployment(
        artifact=artifact,
        eval_report=body.eval_report_summary,
        confidence=body.confidence,
    )
    return StartDeploymentResponse(
        deployment_id=state.deployment_id,
        status=state.status,
    )


@router.get("/api/v1/deployments/{deployment_id}")
async def get_deployment(
    deployment_id: str,
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> DeploymentState:
    """Get the status of a deployment."""
    state = await manager.get_deployment_status(DeploymentId(deployment_id))
    if state is None:
        raise HTTPException(status_code=404, detail=f"Deployment {deployment_id} not found")
    return state


@router.get("/api/v1/deployments")
async def list_deployments(
    status: str | None = Query(default=None, description="Filter by deployment status."),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> list[DeploymentState]:
    """List deployments with optional status filter and pagination."""
    return manager.list_deployments(status_filter=status, offset=offset, limit=limit)


@router.post("/api/v1/deployments/{deployment_id}/rollback", response_model=ActionResponse)
async def rollback_deployment(
    deployment_id: str,
    body: RollbackRequest,
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> ActionResponse:
    """Manually trigger a rollback for an in-progress deployment."""
    success = await manager.trigger_rollback(
        DeploymentId(deployment_id),
        reason=body.reason,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to trigger rollback")
    return ActionResponse(success=True, message=f"Rollback requested for {deployment_id}")


@router.post("/api/v1/deployments/{deployment_id}/cancel", response_model=ActionResponse)
async def cancel_deployment(
    deployment_id: str,
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> ActionResponse:
    """Cancel an in-progress deployment."""
    success = await manager.cancel_deployment(DeploymentId(deployment_id))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel deployment")
    return ActionResponse(success=True, message=f"Cancellation requested for {deployment_id}")


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Service health check endpoint."""
    status = HealthStatus.HEALTHY

    try:
        get_pipeline_manager()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    uptime = time.monotonic() - getattr(request.app.state, "started_at", time.monotonic())
    return HealthResponse(
        service="deployment-pipeline",
        status=status,
        uptime_seconds=round(uptime, 2),
    )
