"""FastAPI router for the World State Ledger service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from architect_common.enums import HealthStatus
from architect_common.errors import LedgerVersionNotFoundError
from world_state_ledger.api.dependencies import EventLogDep, StateManagerDep
from world_state_ledger.models import Proposal

router = APIRouter()


# ── State endpoints ──────────────────────────────────────────────────


@router.get("/state", summary="Get current world state")
async def get_current_state(manager: StateManagerDep) -> dict[str, Any]:
    """Return the current (latest) world state snapshot."""
    state = await manager.get_current()
    return state.model_dump(mode="json")


@router.get("/state/{version}", summary="Get historical world state")
async def get_state_version(version: int, manager: StateManagerDep) -> dict[str, Any]:
    """Return a specific historical version of the world state."""
    try:
        state = await manager.get_version(version)
    except LedgerVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return state.model_dump(mode="json")


# ── Proposal endpoints ───────────────────────────────────────────────


@router.post(
    "/proposals",
    summary="Submit a state mutation proposal",
    status_code=status.HTTP_201_CREATED,
)
async def submit_proposal(proposal: Proposal, manager: StateManagerDep) -> dict[str, str]:
    """Accept a proposal from an agent and persist it for later validation."""
    proposal_id = await manager.submit_proposal(proposal)
    return {"proposal_id": proposal_id}


@router.post(
    "/proposals/{proposal_id}/commit",
    summary="Validate and commit a proposal",
)
async def commit_proposal(proposal_id: str, manager: StateManagerDep) -> dict[str, Any]:
    """Validate the pending proposal and, if valid, commit it to the ledger."""
    try:
        accepted = await manager.validate_and_commit(proposal_id)
    except LedgerVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return {"proposal_id": proposal_id, "accepted": accepted}


# ── Event log ────────────────────────────────────────────────────────


@router.get("/events", summary="Query the event log")
async def query_events(
    event_log: EventLogDep,
    event_type: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Return event log entries matching the given filters."""
    return await event_log.query(
        event_type=event_type,
        task_id=task_id,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )


# ── Health ───────────────────────────────────────────────────────────


@router.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": HealthStatus.HEALTHY, "service": "world-state-ledger"}
