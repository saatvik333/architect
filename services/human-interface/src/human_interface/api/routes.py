"""FastAPI route definitions for the Human Interface."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import (
    ApprovalGateStatus,
    EscalationCategory,
    EscalationSeverity,
    EscalationStatus,
    HealthStatus,
)
from architect_common.logging import get_logger
from architect_common.types import (
    ApprovalGateId,
    EscalationId,
    new_approval_gate_id,
    new_escalation_id,
    utcnow,
)
from architect_db.models.escalation import ApprovalGate, ApprovalVote, Escalation
from architect_db.repositories.escalation_repo import (
    ApprovalGateRepository,
    ApprovalVoteRepository,
    EscalationRepository,
)
from human_interface.config import HumanInterfaceConfig
from human_interface.models import (
    ActivityEvent,
    ApprovalGateResponse,
    CreateApprovalGateRequest,
    CreateEscalationRequest,
    EscalationResponse,
    EscalationStatsResponse,
    ProgressSummary,
    ResolveEscalationRequest,
    VoteRequest,
    WebSocketMessage,
)
from human_interface.ws_manager import WebSocketManager

from .dependencies import get_config, get_http_client, get_session_factory, get_ws_manager

logger = get_logger(component="human_interface.api.routes")

router = APIRouter()

_SERVICE_STARTED_AT = time.monotonic()


# ── Request / Response schemas ────────────────────────────────────


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "human-interface"
    status: HealthStatus
    uptime_seconds: float = 0.0


# ── Helpers ───────────────────────────────────────────────────────


def _escalation_to_response(esc: Escalation) -> EscalationResponse:
    """Convert an ORM Escalation to an API response model."""
    options_raw: list[dict[str, Any]] = esc.options or []
    return EscalationResponse(
        id=EscalationId(esc.id),
        source_agent_id=esc.source_agent_id,
        source_task_id=esc.source_task_id,
        summary=esc.summary,
        category=EscalationCategory(esc.category),
        severity=EscalationSeverity(esc.severity),
        options=options_raw,
        recommended_option=esc.recommended_option,
        reasoning=esc.reasoning,
        risk_if_wrong=esc.risk_if_wrong,
        status=EscalationStatus(esc.status),
        resolved_by=esc.resolved_by,
        resolution=esc.resolution,
        created_at=esc.created_at,
        expires_at=esc.expires_at,
        resolved_at=esc.resolved_at,
    )


def _gate_to_response(gate: ApprovalGate) -> ApprovalGateResponse:
    """Convert an ORM ApprovalGate to an API response model."""
    return ApprovalGateResponse(
        id=ApprovalGateId(gate.id),
        action_type=gate.action_type,
        resource_id=gate.resource_id,
        required_approvals=gate.required_approvals,
        current_approvals=gate.current_approvals,
        status=ApprovalGateStatus(gate.status),
        context=gate.context,
        created_at=gate.created_at,
        expires_at=gate.expires_at,
        resolved_at=gate.resolved_at,
    )


# ── Escalation endpoints ─────────────────────────────────────────


@router.post("/api/v1/escalations", response_model=EscalationResponse, status_code=201)
async def create_escalation(
    body: CreateEscalationRequest,
    config: HumanInterfaceConfig = Depends(get_config),
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EscalationResponse:
    """Create a new escalation and broadcast to connected clients."""
    now = utcnow()
    expires_minutes = body.expires_in_minutes or config.default_escalation_expiry_minutes
    expires_at = now + timedelta(minutes=expires_minutes)

    escalation_id = new_escalation_id()
    options_data = [opt.model_dump(mode="json") for opt in body.options] if body.options else None

    async with session_factory() as session:
        repo = EscalationRepository(session)
        entity = Escalation(
            id=escalation_id,
            source_agent_id=body.source_agent_id,
            source_task_id=body.source_task_id,
            correlation_id=body.correlation_id,
            summary=body.summary,
            category=body.category.value,
            severity=body.severity.value,
            options=options_data,
            recommended_option=body.recommended_option,
            reasoning=body.reasoning,
            risk_if_wrong=body.risk_if_wrong,
            status=EscalationStatus.PENDING.value,
            decision_confidence=body.decision_confidence,
            is_security_critical=body.is_security_critical,
            cost_impact_pct=body.cost_impact_pct,
            created_at=now,
            expires_at=expires_at,
        )
        await repo.create(entity)
        await session.commit()

    response = EscalationResponse(
        id=EscalationId(escalation_id),
        source_agent_id=body.source_agent_id,
        source_task_id=body.source_task_id,
        summary=body.summary,
        category=body.category,
        severity=body.severity,
        options=body.options,
        recommended_option=body.recommended_option,
        reasoning=body.reasoning,
        risk_if_wrong=body.risk_if_wrong,
        status=EscalationStatus.PENDING,
        created_at=now,
        expires_at=expires_at,
    )

    # Broadcast to WebSocket clients.
    await ws_manager.broadcast(
        WebSocketMessage(
            type="escalation_created",
            data=response.model_dump(mode="json"),
        ).model_dump(mode="json")
    )

    logger.info("escalation created", escalation_id=escalation_id)
    return response


@router.get("/api/v1/escalations", response_model=list[EscalationResponse])
async def list_escalations(
    status: EscalationStatus | None = Query(default=None),
    category: EscalationCategory | None = Query(default=None),
    severity: EscalationSeverity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[EscalationResponse]:
    """List escalations with optional filters."""
    async with session_factory() as session:
        repo = EscalationRepository(session)
        if status is not None:
            rows = await repo.get_by_status(status.value, limit=limit, offset=offset)
        else:
            rows = await repo.list_all(limit=limit, offset=offset)

    results = [_escalation_to_response(r) for r in rows]

    # Apply in-memory filters for category/severity if provided.
    if category is not None:
        results = [r for r in results if r.category == category]
    if severity is not None:
        results = [r for r in results if r.severity == severity]

    return results


@router.get("/api/v1/escalations/stats", response_model=EscalationStatsResponse)
async def get_escalation_stats(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EscalationStatsResponse:
    """Return aggregated escalation statistics."""
    async with session_factory() as session:
        repo = EscalationRepository(session)
        stats = await repo.get_stats()

    return EscalationStatsResponse(
        total=stats["total"],
        pending=stats["pending"],
        resolved=stats["resolved"],
        expired=stats["expired"],
    )


@router.get("/api/v1/escalations/{escalation_id}", response_model=EscalationResponse)
async def get_escalation(
    escalation_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EscalationResponse:
    """Get a single escalation by ID."""
    async with session_factory() as session:
        repo = EscalationRepository(session)
        entity = await repo.get_by_id(escalation_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    return _escalation_to_response(entity)


@router.post(
    "/api/v1/escalations/{escalation_id}/resolve",
    response_model=EscalationResponse,
)
async def resolve_escalation(
    escalation_id: str,
    body: ResolveEscalationRequest,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EscalationResponse:
    """Resolve an escalation with a human decision."""
    async with session_factory() as session:
        repo = EscalationRepository(session)
        entity = await repo.resolve(
            escalation_id,
            resolved_by=body.resolved_by,
            resolution=body.resolution,
            resolution_details=body.custom_input,
        )
        await session.commit()

    if entity is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    response = _escalation_to_response(entity)

    # Broadcast resolution to WebSocket clients.
    await ws_manager.broadcast(
        WebSocketMessage(
            type="escalation_resolved",
            data=response.model_dump(mode="json"),
        ).model_dump(mode="json")
    )

    logger.info("escalation resolved", escalation_id=escalation_id)
    return response


# ── Approval gate endpoints ──────────────────────────────────────


@router.post("/api/v1/approval-gates", response_model=ApprovalGateResponse, status_code=201)
async def create_approval_gate(
    body: CreateApprovalGateRequest,
    config: HumanInterfaceConfig = Depends(get_config),
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ApprovalGateResponse:
    """Create a new approval gate."""
    now = utcnow()
    gate_id = new_approval_gate_id()
    expires_at = (
        now + timedelta(minutes=body.expires_in_minutes)
        if body.expires_in_minutes
        else now + timedelta(minutes=config.default_escalation_expiry_minutes)
    )

    async with session_factory() as session:
        repo = ApprovalGateRepository(session)
        entity = ApprovalGate(
            id=gate_id,
            action_type=body.action_type,
            resource_id=body.resource_id,
            required_approvals=body.required_approvals,
            current_approvals=0,
            status=ApprovalGateStatus.PENDING.value,
            context=body.context,
            created_at=now,
            expires_at=expires_at,
        )
        await repo.create(entity)
        await session.commit()

    response = ApprovalGateResponse(
        id=ApprovalGateId(gate_id),
        action_type=body.action_type,
        resource_id=body.resource_id,
        required_approvals=body.required_approvals,
        current_approvals=0,
        status=ApprovalGateStatus.PENDING,
        context=body.context,
        created_at=now,
        expires_at=expires_at,
    )

    await ws_manager.broadcast(
        WebSocketMessage(
            type="approval_gate_created",
            data=response.model_dump(mode="json"),
        ).model_dump(mode="json")
    )

    logger.info("approval gate created", gate_id=gate_id)
    return response


@router.get("/api/v1/approval-gates", response_model=list[ApprovalGateResponse])
async def list_approval_gates(
    status: ApprovalGateStatus | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[ApprovalGateResponse]:
    """List approval gates with optional filters."""
    async with session_factory() as session:
        repo = ApprovalGateRepository(session)
        if status == ApprovalGateStatus.PENDING:
            rows = await repo.get_pending(limit=limit)
        else:
            rows = await repo.list_all(limit=limit, offset=offset)

    results = [_gate_to_response(r) for r in rows]

    if action_type is not None:
        results = [r for r in results if r.action_type == action_type]

    return results


@router.get("/api/v1/approval-gates/{gate_id}", response_model=ApprovalGateResponse)
async def get_approval_gate(
    gate_id: str,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ApprovalGateResponse:
    """Get a single approval gate by ID."""
    async with session_factory() as session:
        repo = ApprovalGateRepository(session)
        entity = await repo.get_by_id(gate_id)

    if entity is None:
        raise HTTPException(status_code=404, detail="Approval gate not found")

    return _gate_to_response(entity)


@router.post("/api/v1/approval-gates/{gate_id}/vote", response_model=ApprovalGateResponse)
async def cast_vote(
    gate_id: str,
    body: VoteRequest,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ApprovalGateResponse:
    """Cast a vote on an approval gate. Auto-resolves if enough votes."""
    async with session_factory() as session:
        gate_repo = ApprovalGateRepository(session)
        vote_repo = ApprovalVoteRepository(session)

        gate = await gate_repo.get_by_id(gate_id)
        if gate is None:
            raise HTTPException(status_code=404, detail="Approval gate not found")

        if gate.status != ApprovalGateStatus.PENDING.value:
            raise HTTPException(status_code=400, detail="Gate is no longer pending")

        # Record the vote.
        vote = ApprovalVote(
            gate_id=gate_id,
            voter=body.voter,
            decision=body.decision,
            comment=body.comment,
        )
        await vote_repo.create(vote)

        # Update approval count and check for auto-resolution.
        if body.decision == "approve":
            gate.current_approvals += 1
            if gate.current_approvals >= gate.required_approvals:
                gate.status = ApprovalGateStatus.APPROVED.value
                gate.resolved_at = utcnow()
        elif body.decision == "deny":
            gate.status = ApprovalGateStatus.DENIED.value
            gate.resolved_at = utcnow()

        await session.flush()
        await session.commit()

        result = _gate_to_response(gate)

    await ws_manager.broadcast(
        WebSocketMessage(
            type="approval_vote_cast",
            data=result.model_dump(mode="json"),
        ).model_dump(mode="json")
    )

    logger.info(
        "vote cast on approval gate",
        gate_id=gate_id,
        voter=body.voter,
        decision=body.decision,
    )
    return result


# ── Progress endpoints ───────────────────────────────────────────


@router.get("/api/v1/progress", response_model=ProgressSummary)
async def get_progress(
    config: HumanInterfaceConfig = Depends(get_config),
) -> ProgressSummary:
    """Aggregate progress from WSL, task graph, and budget services.

    Gracefully falls back to defaults if upstream services are unavailable.
    """
    import httpx as httpx_mod

    http_client: httpx_mod.AsyncClient
    try:
        http_client = get_http_client()
    except RuntimeError:
        http_client = httpx_mod.AsyncClient(timeout=5.0)

    tasks_completed = 0
    tasks_total = 0
    budget_consumed_pct = 0.0

    # Fetch task graph stats.
    try:
        resp = await http_client.get(f"{config.task_graph_url}/api/v1/tasks/stats")
        if resp.status_code == 200:
            data = resp.json()
            tasks_completed = data.get("completed", 0)
            tasks_total = data.get("total", 0)
    except Exception:
        logger.debug("task graph service unavailable for progress")

    # Fetch budget snapshot.
    try:
        resp = await http_client.get(f"{config.economic_governor_url}/api/v1/budget/status")
        if resp.status_code == 200:
            data = resp.json()
            budget_consumed_pct = data.get("consumed_pct", 0.0)
    except Exception:
        logger.debug("economic governor unavailable for progress")

    completion_pct = (tasks_completed / tasks_total * 100) if tasks_total > 0 else 0.0

    return ProgressSummary(
        tasks_completed=tasks_completed,
        tasks_total=tasks_total,
        completion_pct=round(completion_pct, 1),
        budget_consumed_pct=round(budget_consumed_pct, 1),
    )


@router.get("/api/v1/activity", response_model=list[ActivityEvent])
async def get_activity(
    limit: int = Query(default=20, ge=1, le=200),
) -> list[ActivityEvent]:
    """Return recent activity events.

    In a production deployment this would read from a persistent activity
    log.  For now it returns an empty list as a stub.
    """
    return []


# ── WebSocket ────────────────────────────────────────────────────


@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
) -> None:
    """Real-time WebSocket push to dashboard clients."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; clients may send pings or commands.
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ── Health ───────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        uptime_seconds=round(time.monotonic() - _SERVICE_STARTED_AT, 1),
    )
