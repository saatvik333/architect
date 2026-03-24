"""ARCHITECT API Gateway — unified HTTP entry point for the ARCHITECT system."""

from __future__ import annotations

import hmac
import time
import uuid as _uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, ClassVar

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

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
from architect_observability import init_observability

logger = get_logger(component="api_gateway")

# Paths exempt from API key authentication.
_AUTH_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/api/v1/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


# ── Dependency injection helpers ──────────────────────────────────


@lru_cache
def get_config() -> GatewayConfig:
    """Return the cached gateway configuration."""
    return GatewayConfig()


async def get_client(request: Request) -> ServiceClient:
    """Return the ServiceClient stored on app state."""
    return request.app.state.client  # type: ignore[no-any-return]


# ── Lifespan ──────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Start/stop the shared service client."""
    config = get_config()
    client = ServiceClient(config)
    await client.startup()
    application.state.client = client
    yield
    await client.shutdown()


app = FastAPI(
    title="ARCHITECT API Gateway",
    description="Unified entry point for the ARCHITECT autonomous coding system.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Middleware classes ─────────────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # HSTS only in non-dev environments
        config = get_config()
        if config.environment != "dev":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``Content-Length`` exceeds the configured limit."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        config = get_config()
        max_bytes = config.max_request_body_bytes
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large (max {max_bytes} bytes)"},
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter keyed by client IP.

    Uses an in-memory store suitable for single-instance deployments.
    """

    # Class-level state so tests can clear it.
    _windows: ClassVar[dict[str, list[float]]] = defaultdict(list)

    @classmethod
    def reset(cls) -> None:
        """Clear all rate limit windows (for testing)."""
        cls._windows.clear()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Exempt health endpoints from rate limiting
        if request.url.path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        config = get_config()
        limit = config.rate_limit_per_minute
        if limit <= 0:
            return await call_next(request)

        # Use API key (if present) or client IP as rate limit key
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and len(auth_header) > 7:
            key = f"key:{auth_header[7:][:16]}"
        else:
            key = f"ip:{request.client.host}" if request.client else "ip:unknown"

        now = time.monotonic()
        window_start = now - 60.0

        # Prune old entries
        timestamps = self._windows[key]
        self._windows[key] = [t for t in timestamps if t > window_start]
        timestamps = self._windows[key]

        if len(timestamps) >= limit:
            retry_after = int(60 - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        return await call_next(request)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate ``Authorization: Bearer <key>`` on every non-exempt request.

    Reads config lazily via :func:`get_config` so that test monkeypatches
    take effect.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        config = get_config()

        # Skip auth when disabled
        if not config.auth_enabled:
            return await call_next(request)

        # Exempt paths and CORS preflight
        if request.url.path in _AUTH_EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        api_keys = config.api_keys

        # No keys configured = open access (development only)
        if not api_keys:
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        token = auth_header[7:]  # len("Bearer ") == 7

        # Constant-time comparison against all configured keys
        if not any(hmac.compare_digest(token, key) for key in api_keys):
            logger.warning(
                "auth_rejected",
                key_prefix=token[:8] if len(token) >= 8 else "***",
                path=request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate a unique request ID for every request and set it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(_uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ── Register middleware ────────────────────────────────────────────
# Execution order: CORS → RequestID → RateLimit → Auth → SizeLimit → SecurityHeaders → handler
# Starlette runs outermost-added middleware first, so add in reverse of desired order.

_startup_config = get_config()

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(APIKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_startup_config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# ── Observability ─────────────────────────────────────────────────

init_observability(app, "api-gateway")


# ── Exception handlers ──────────────────────────────────────────────


@app.exception_handler(httpx.HTTPStatusError)
async def http_status_error_handler(_request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """Return a generic error to the client; log upstream details server-side only."""
    upstream_body = exc.response.text
    logger.error(
        "upstream HTTP error",
        status_code=exc.response.status_code,
        # Truncate upstream body in logs to avoid leaking large payloads with
        # potentially sensitive data.
        upstream_body=upstream_body[:500] if upstream_body else "",
        url=str(exc.request.url),
    )
    # Map upstream status to a safe client-facing status.  Preserve 4xx codes
    # so the client knows whether it was a bad request vs not-found, but never
    # expose raw 5xx — always return 502 (Bad Gateway) for upstream server errors.
    upstream_status = exc.response.status_code
    client_status = 502 if upstream_status >= 500 else upstream_status

    return JSONResponse(
        status_code=client_status,
        content={"detail": "An error occurred while processing the request."},
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
async def health_check(client: ServiceClient = Depends(get_client)) -> HealthResponse:
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
            await client.get_service_health(service_name)
            services[service_name] = "healthy"
        except Exception:
            services[service_name] = "unhealthy"
            overall = "degraded"

    return HealthResponse(status=overall, services=services)


@app.get("/api/v1/health")
async def health_check_prefixed(client: ServiceClient = Depends(get_client)) -> HealthResponse:
    """Health check at /api/v1/health — alias for /health."""
    return await health_check(client)


@app.get("/api/v1/tasks")
async def list_tasks(
    client: ServiceClient = Depends(get_client),
    status: str | None = None,
    task_type: str | None = Query(None, alias="type"),
) -> list[dict[str, Any]]:
    """List all tasks, optionally filtered by status or type."""
    params: dict[str, str] = {}
    if status is not None:
        params["status"] = status
    if task_type is not None:
        params["type"] = task_type
    result = await client.list_tasks(params)
    # task-graph returns {"tasks": [...], "total": N}, extract the list
    if isinstance(result, dict) and "tasks" in result:
        return result["tasks"]
    return result


@app.post("/api/v1/tasks")
async def create_task(
    payload: TaskSubmitRequest,
    client: ServiceClient = Depends(get_client),
) -> TaskSubmitResponse:
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
    result = await client.submit_task(spec_payload)
    # task-graph returns {task_count, task_ids, execution_order, validation_errors}
    task_ids = result.get("task_ids", [])
    return TaskSubmitResponse(
        task_id=task_ids[0] if task_ids else "unknown",
        status="accepted",
    )


@app.get("/api/v1/tasks/{task_id}")
async def get_task(
    task_id: str,
    client: ServiceClient = Depends(get_client),
) -> TaskStatusResponse:
    """Retrieve task status."""
    result = await client.get_task_status(task_id)
    # task-graph returns TaskResponse with 'id', translate to gateway's 'task_id'
    return TaskStatusResponse(
        task_id=result.get("id", task_id),
        name=result.get("description", ""),
        status=result.get("status", "unknown"),
    )


@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(
    task_id: str,
    follow: bool = False,
    client: ServiceClient = Depends(get_client),
) -> TaskLogsResponse:
    """Retrieve logs for a task."""
    result = await client.get_task_logs(task_id, follow=follow)
    return TaskLogsResponse.model_validate(result)


@app.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    body: CancelRequest | None = None,
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Cancel a running task."""
    force = body.force if body else False
    return await client.cancel_task(task_id, force=force)


@app.get("/api/v1/tasks/{task_id}/proposals")
async def get_task_proposals(
    task_id: str,
    client: ServiceClient = Depends(get_client),
) -> list[dict[str, Any]]:
    """Retrieve proposals for a task."""
    return await client.get_proposals(task_id)


@app.get("/api/v1/proposals")
async def list_proposals(
    task_id: str | None = None,
    client: ServiceClient = Depends(get_client),
) -> list[dict[str, Any]]:
    """List proposals, optionally filtered by task_id."""
    if task_id is not None:
        return await client.get_proposals(task_id)
    # Without task_id filter, query the world-state events endpoint
    # for proposal-related events
    return await client.list_proposals()


@app.get("/api/v1/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: str,
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Retrieve a single proposal by ID."""
    return await client.get_proposal(proposal_id)


@app.get("/api/v1/state")
async def get_world_state(client: ServiceClient = Depends(get_client)) -> WorldStateResponse:
    """Retrieve the current world state."""
    result = await client.get_world_state()
    return WorldStateResponse.model_validate(result)


@app.post("/api/v1/state/proposals")
async def submit_proposal(
    body: ProposalSubmitRequest,
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Submit a raw proposal to the world state ledger."""
    return await client.submit_proposal(body.model_dump())


# ── Phase 2: Spec Engine ──────────────────────────────────────────


@app.post("/api/v1/specs")
async def create_spec(
    payload: dict[str, Any],
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Submit a natural-language task description for spec parsing."""
    return await client.create_spec(payload)


@app.get("/api/v1/specs/{spec_id}")
async def get_spec(
    spec_id: str,
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Retrieve a parsed specification."""
    return await client.get_spec(spec_id)


@app.post("/api/v1/specs/{spec_id}/clarify")
async def clarify_spec(
    spec_id: str,
    payload: dict[str, Any],
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Answer clarification questions for an ambiguous spec."""
    return await client.clarify_spec(spec_id, payload)


# ── Phase 2: Multi-Model Router ──────────────────────────────────


@app.post("/api/v1/route")
async def route_task(
    payload: dict[str, Any],
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Get a routing decision for a task."""
    return await client.route_task(payload)


@app.get("/api/v1/route/stats")
async def get_routing_stats(client: ServiceClient = Depends(get_client)) -> dict[str, Any]:
    """Retrieve routing statistics."""
    return await client.get_routing_stats()


# ── Phase 2: Codebase Comprehension ──────────────────────────────


@app.post("/api/v1/index")
async def index_codebase(
    payload: dict[str, Any],
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Index a codebase directory."""
    return await client.index_codebase(payload)


@app.get("/api/v1/context")
async def get_code_context(
    task_description: str = "",
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Get relevant code context for a task description."""
    return await client.get_code_context({"task_description": task_description})


@app.get("/api/v1/symbols")
async def search_symbols(
    query: str = "",
    limit: int = 20,
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Search for code symbols."""
    return await client.search_symbols({"query": query, "limit": limit})


# ── Phase 2: Agent Communication Bus ─────────────────────────────


@app.get("/api/v1/bus/stats")
async def get_bus_stats(client: ServiceClient = Depends(get_client)) -> dict[str, Any]:
    """Get message bus statistics."""
    return await client.get_bus_stats()


@app.post("/api/v1/bus/publish")
async def publish_message(
    payload: dict[str, Any],
    client: ServiceClient = Depends(get_client),
) -> dict[str, Any]:
    """Publish a message to the agent communication bus."""
    return await client.publish_message(payload)
