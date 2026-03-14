"""ARCHITECT API Gateway — unified HTTP entry point for the ARCHITECT system."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
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

logger = logging.getLogger(__name__)

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
    logger.error("Backend service unavailable: %s", exc)
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

    for service_name in ("task-graph", "world-state", "sandbox", "eval-engine", "coding-agent"):
        try:
            await _client.get_service_health(service_name)
            services[service_name] = "healthy"
        except Exception:
            services[service_name] = "unhealthy"
            overall = "degraded"

    return HealthResponse(status=overall, services=services)


@app.post("/api/v1/tasks")
async def create_task(payload: TaskSubmitRequest) -> TaskSubmitResponse:
    """Submit a new task specification."""
    result = await _client.submit_task(payload.model_dump())
    return TaskSubmitResponse.model_validate(result)


@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str) -> TaskStatusResponse:
    """Retrieve task status."""
    result = await _client.get_task_status(task_id)
    return TaskStatusResponse.model_validate(result)


@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, follow: bool = False) -> TaskLogsResponse:
    """Retrieve logs for a task."""
    result = await _client.get_task_logs(task_id, follow=follow)
    return TaskLogsResponse.model_validate(result)


@app.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, body: CancelRequest | None = None) -> dict:
    """Cancel a running task."""
    force = body.force if body else False
    return await _client.cancel_task(task_id, force=force)


@app.get("/api/v1/tasks/{task_id}/proposals")
async def get_task_proposals(task_id: str) -> list[dict]:
    """Retrieve proposals for a task."""
    return await _client.get_proposals(task_id)


@app.get("/api/v1/proposals/{proposal_id}")
async def get_proposal(proposal_id: str) -> dict:
    """Retrieve a single proposal by ID."""
    return await _client.get_proposal(proposal_id)


@app.get("/api/v1/state")
async def get_world_state() -> WorldStateResponse:
    """Retrieve the current world state."""
    result = await _client.get_world_state()
    return WorldStateResponse.model_validate(result)


@app.post("/api/v1/state/proposals")
async def submit_proposal(body: ProposalSubmitRequest) -> dict:
    """Submit a raw proposal to the world state ledger."""
    return await _client.submit_proposal(body.model_dump())
