"""ARCHITECT API Gateway — unified HTTP entry point for the ARCHITECT system."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api_gateway.config import GatewayConfig
from api_gateway.models import (
    CancelRequest,
    HealthResponse,
    ProposalSubmitRequest,
    TaskLogsResponse,
    TaskStatusResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    WorldStateResponse,
)
from api_gateway.service_client import ServiceClient
from architect_common.logging import get_logger

logger = get_logger(component="api_gateway")

_config = GatewayConfig()
_client = ServiceClient(_config)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start/stop the shared service client."""
    await _client.startup()
    yield
    await _client.shutdown()


app = FastAPI(
    title="ARCHITECT API Gateway",
    description="Unified entry point for the ARCHITECT autonomous coding system.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ──────────────────────────────────────────────


@app.exception_handler(httpx.HTTPStatusError)
async def http_status_error_handler(_request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """Forward upstream HTTP errors to the client."""
    return JSONResponse(
        status_code=exc.response.status_code,
        content={"detail": exc.response.text},
    )


@app.exception_handler(httpx.ConnectError)
async def connect_error_handler(_request: Request, exc: httpx.ConnectError) -> JSONResponse:
    """Return 502 when a backend service is unreachable."""
    logger.error("backend service unavailable", error=str(exc))
    return JSONResponse(
        status_code=502,
        content={"detail": "Backend service unavailable"},
    )


# ── Routes ───────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> HealthResponse:
    """Aggregate health check across all backend services."""
    services: dict[str, str] = {}
    overall = "healthy"

    for service_name in (
        "task-graph",
        "world-state",
        "sandbox",
        "eval-engine",
        "coding-agent",
        "spec-engine",
        "router",
        "codebase",
        "comm-bus",
    ):
        try:
            await _client.get_service_health(service_name)
            services[service_name] = "healthy"
        except Exception:
            services[service_name] = "unhealthy"
            overall = "degraded"

    return HealthResponse(status=overall, services=services)


@app.get("/api/v1/health")
async def health_check_prefixed() -> HealthResponse:
    """Health check at /api/v1/health — alias for /health."""
    return await health_check()


@app.get("/api/v1/tasks")
async def list_tasks(
    status: str | None = None,
    task_type: str | None = Query(None, alias="type"),
) -> list[dict[str, Any]]:
    """List all tasks, optionally filtered by status or type."""
    params: dict[str, str] = {}
    if status is not None:
        params["status"] = status
    if task_type is not None:
        params["type"] = task_type
    result = await _client.list_tasks(params)
    # task-graph returns {"tasks": [...], "total": N}, extract the list
    if isinstance(result, dict) and "tasks" in result:
        return result["tasks"]  # type: ignore[return-value]
    return result  # type: ignore[return-value]


@app.post("/api/v1/tasks")
async def create_task(payload: TaskSubmitRequest) -> TaskSubmitResponse:
    """Submit a new task specification."""
    # Translate gateway request to task-graph-engine's SubmitSpecRequest format
    spec_payload = {
        "spec": {
            "name": payload.name,
            "description": payload.description,
            "priority": payload.priority,
            **(payload.spec or {}),
        },
        "use_llm": False,
    }
    result = await _client.submit_task(spec_payload)
    # task-graph returns {task_count, task_ids, execution_order, validation_errors}
    task_ids = result.get("task_ids", [])
    return TaskSubmitResponse(
        task_id=task_ids[0] if task_ids else "unknown",
        status="accepted",
    )


@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str) -> TaskStatusResponse:
    """Retrieve task status."""
    result = await _client.get_task_status(task_id)
    # task-graph returns TaskResponse with 'id', translate to gateway's 'task_id'
    return TaskStatusResponse(
        task_id=result.get("id", task_id),
        name=result.get("description", ""),
        status=result.get("status", "unknown"),
    )


@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, follow: bool = False) -> TaskLogsResponse:
    """Retrieve logs for a task."""
    result = await _client.get_task_logs(task_id, follow=follow)
    return TaskLogsResponse.model_validate(result)


@app.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, body: CancelRequest | None = None) -> dict[str, Any]:
    """Cancel a running task."""
    force = body.force if body else False
    return await _client.cancel_task(task_id, force=force)


@app.get("/api/v1/tasks/{task_id}/proposals")
async def get_task_proposals(task_id: str) -> list[dict[str, Any]]:
    """Retrieve proposals for a task."""
    return await _client.get_proposals(task_id)


@app.get("/api/v1/proposals")
async def list_proposals(task_id: str | None = None) -> list[dict[str, Any]]:
    """List proposals, optionally filtered by task_id."""
    if task_id is not None:
        return await _client.get_proposals(task_id)
    # Without task_id filter, query the world-state events endpoint
    # for proposal-related events
    return await _client.list_proposals()


@app.get("/api/v1/proposals/{proposal_id}")
async def get_proposal(proposal_id: str) -> dict[str, Any]:
    """Retrieve a single proposal by ID."""
    return await _client.get_proposal(proposal_id)


@app.get("/api/v1/state")
async def get_world_state() -> WorldStateResponse:
    """Retrieve the current world state."""
    result = await _client.get_world_state()
    return WorldStateResponse.model_validate(result)


@app.post("/api/v1/state/proposals")
async def submit_proposal(body: ProposalSubmitRequest) -> dict[str, Any]:
    """Submit a raw proposal to the world state ledger."""
    return await _client.submit_proposal(body.model_dump())


# ── Phase 2: Spec Engine ──────────────────────────────────────────


@app.post("/api/v1/specs")
async def create_spec(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a natural-language task description for spec parsing."""
    return await _client.create_spec(payload)


@app.get("/api/v1/specs/{spec_id}")
async def get_spec(spec_id: str) -> dict[str, Any]:
    """Retrieve a parsed specification."""
    return await _client.get_spec(spec_id)


@app.post("/api/v1/specs/{spec_id}/clarify")
async def clarify_spec(spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Answer clarification questions for an ambiguous spec."""
    return await _client.clarify_spec(spec_id, payload)


# ── Phase 2: Multi-Model Router ──────────────────────────────────


@app.post("/api/v1/route")
async def route_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Get a routing decision for a task."""
    return await _client.route_task(payload)


@app.get("/api/v1/route/stats")
async def get_routing_stats() -> dict[str, Any]:
    """Retrieve routing statistics."""
    return await _client.get_routing_stats()


# ── Phase 2: Codebase Comprehension ──────────────────────────────


@app.post("/api/v1/index")
async def index_codebase(payload: dict[str, Any]) -> dict[str, Any]:
    """Index a codebase directory."""
    return await _client.index_codebase(payload)


@app.get("/api/v1/context")
async def get_code_context(task_description: str = "") -> dict[str, Any]:
    """Get relevant code context for a task description."""
    return await _client.get_code_context({"task_description": task_description})


@app.get("/api/v1/symbols")
async def search_symbols(query: str = "", limit: int = 20) -> dict[str, Any]:
    """Search for code symbols."""
    return await _client.search_symbols({"query": query, "limit": limit})


# ── Phase 2: Agent Communication Bus ─────────────────────────────


@app.get("/api/v1/bus/stats")
async def get_bus_stats() -> dict[str, Any]:
    """Get message bus statistics."""
    return await _client.get_bus_stats()


@app.post("/api/v1/bus/publish")
async def publish_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Publish a message to the agent communication bus."""
    return await _client.publish_message(payload)
