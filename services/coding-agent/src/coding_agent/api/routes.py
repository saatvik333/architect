"""FastAPI route definitions for the Coding Agent."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus, StatusEnum
from architect_common.types import TaskId, new_agent_id
from coding_agent.agent import CodingAgentLoop
from coding_agent.api.dependencies import get_agent_loop
from coding_agent.models import (
    AgentConfig,
    AgentRun,
    CodebaseContext,
    SpecContext,
)

router = APIRouter()

# ── In-memory run store (production would use a database) ─────────────
_MAX_RUN_STORE_SIZE = 1000
_run_store: OrderedDict[str, dict[str, Any]] = OrderedDict()


# ── Request / Response schemas ────────────────────────────────────────


class ExecuteRequest(BaseModel):
    """Request body for POST /agent/execute."""

    task_id: str = Field(description="Branded task identifier.")
    spec_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialised SpecContext.",
    )
    codebase_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialised CodebaseContext.",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialised AgentConfig overrides.",
    )


class ExecuteResponse(BaseModel):
    """Response body for POST /agent/execute."""

    agent_id: str
    task_id: str
    status: StatusEnum
    files_generated: int
    output: dict[str, Any] | None = None


class AgentStatusResponse(BaseModel):
    """Response body for GET /agent/{agent_id}."""

    agent_id: str
    task_id: str
    status: StatusEnum
    output: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "coding-agent"
    status: HealthStatus


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/agent/execute", response_model=ExecuteResponse)
async def execute_agent(
    body: ExecuteRequest,
    agent_loop: CodingAgentLoop = Depends(get_agent_loop),
) -> ExecuteResponse:
    """Execute the coding agent on a task."""
    agent_id = new_agent_id()

    run = AgentRun(
        id=agent_id,
        task_id=TaskId(body.task_id),
        config=AgentConfig.model_validate(body.config) if body.config else AgentConfig(),
        spec_context=SpecContext.model_validate(body.spec_context),
        codebase_context=CodebaseContext.model_validate(body.codebase_context),
        status=StatusEnum.RUNNING,
    )

    output = await agent_loop.execute(run)

    output_dict = output.model_dump(mode="json")

    # Prune oldest half when the store exceeds the max size
    if len(_run_store) >= _MAX_RUN_STORE_SIZE:
        to_remove = _MAX_RUN_STORE_SIZE // 2
        for _ in range(to_remove):
            _run_store.popitem(last=False)

    _run_store[str(agent_id)] = {
        "agent_id": str(agent_id),
        "task_id": body.task_id,
        "status": StatusEnum.COMPLETED,
        "output": output_dict,
        "error": None,
    }

    return ExecuteResponse(
        agent_id=str(agent_id),
        task_id=body.task_id,
        status=StatusEnum.COMPLETED,
        files_generated=len(output.files),
        output=output_dict,
    )


@router.get("/agent/{agent_id}", response_model=AgentStatusResponse)
async def get_agent_status(agent_id: str) -> AgentStatusResponse:
    """Get the status and output of an agent run."""
    run_data = _run_store.get(agent_id)
    if run_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No agent run found for agent_id={agent_id}",
        )
    return AgentStatusResponse(**run_data)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)
