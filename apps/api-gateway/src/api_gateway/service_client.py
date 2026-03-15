"""Async HTTP client for proxying requests to backend services."""

from __future__ import annotations

from typing import Any

import httpx

from api_gateway.config import GatewayConfig
from architect_common.logging import get_logger

logger = get_logger(component="api_gateway.service_client")

_SERVICE_URL_MAP = {
    "task-graph": "task_graph_url",
    "world-state": "world_state_url",
    "sandbox": "sandbox_url",
    "eval-engine": "eval_engine_url",
    "coding-agent": "coding_agent_url",
    "spec-engine": "spec_engine_url",
    "router": "multi_model_router_url",
    "codebase": "codebase_comprehension_url",
    "comm-bus": "agent_comm_bus_url",
}

# Per-service read timeouts (seconds) for long-running operations.
_SERVICE_TIMEOUTS: dict[str, float] = {
    "spec-engine": 180.0,
    "coding-agent": 180.0,
    "eval-engine": 120.0,
    "router": 120.0,
}

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class ServiceClient:
    """HTTP client for proxying to backend ARCHITECT services."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Create the shared httpx async client."""
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def shutdown(self) -> None:
        """Close the shared httpx async client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _base_url(self, service: str) -> str:
        attr = _SERVICE_URL_MAP.get(service)
        if attr is None:
            msg = f"Unknown service: {service}"
            raise ValueError(msg)
        return str(getattr(self._config, attr))

    def _timeout_for_service(self, service: str) -> httpx.Timeout:
        """Return a timeout with the read value overridden per service."""
        read = _SERVICE_TIMEOUTS.get(service, _DEFAULT_TIMEOUT.read)
        return httpx.Timeout(
            connect=_DEFAULT_TIMEOUT.connect,
            read=read,
            write=_DEFAULT_TIMEOUT.write,
            pool=_DEFAULT_TIMEOUT.pool,
        )

    async def _request(
        self,
        service: str,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an HTTP request to a backend service.

        Raises ``httpx.HTTPStatusError`` on non-2xx responses.
        """
        if self._client is None:
            msg = "ServiceClient not started — call startup() first"
            raise RuntimeError(msg)

        url = f"{self._base_url(service)}{path}"
        timeout = self._timeout_for_service(service)
        resp = await self._client.request(method, url, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ── Typed methods ────────────────────────────────────────────────

    async def submit_task(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("task-graph", "POST", "/tasks/submit", json=data)

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        return await self._request("task-graph", "GET", f"/tasks/{task_id}")

    async def get_task_logs(self, task_id: str, follow: bool = False) -> dict[str, Any]:
        return await self._request(
            "task-graph", "GET", f"/tasks/{task_id}/logs", params={"follow": follow}
        )

    async def cancel_task(self, task_id: str, force: bool = False) -> dict[str, Any]:
        return await self._request(
            "task-graph", "POST", f"/tasks/{task_id}/cancel", json={"force": force}
        )

    async def get_proposals(self, task_id: str) -> list[dict[str, Any]]:
        return await self._request(  # type: ignore[return-value]
            "world-state", "GET", "/events", params={"task_id": task_id}
        )

    async def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        return await self._request("world-state", "GET", f"/events/{proposal_id}")

    async def submit_proposal(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("world-state", "POST", "/proposals", json=data)

    async def get_world_state(self) -> dict[str, Any]:
        return await self._request("world-state", "GET", "/state")

    async def list_tasks(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._request(  # type: ignore[return-value]
            "task-graph", "GET", "/tasks", params=params
        )

    async def list_proposals(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self._request(  # type: ignore[return-value]
            "world-state", "GET", "/events", params=params
        )

    async def get_service_health(self, service: str) -> dict[str, Any]:
        return await self._request(service, "GET", "/health")

    # ── Phase 2 service methods ───────────────────────────────────

    async def create_spec(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("spec-engine", "POST", "/api/v1/specs", json=data)

    async def get_spec(self, spec_id: str) -> dict[str, Any]:
        return await self._request("spec-engine", "GET", f"/api/v1/specs/{spec_id}")

    async def clarify_spec(self, spec_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "spec-engine", "POST", f"/api/v1/specs/{spec_id}/clarify", json=data
        )

    async def route_task(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("router", "POST", "/api/v1/route", json=data)

    async def get_routing_stats(self) -> dict[str, Any]:
        return await self._request("router", "GET", "/api/v1/route/stats")

    async def index_codebase(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("codebase", "POST", "/api/v1/index", json=data)

    async def get_code_context(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("codebase", "GET", "/api/v1/context", params=params)

    async def search_symbols(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("codebase", "GET", "/api/v1/symbols", params=params)

    async def get_bus_stats(self) -> dict[str, Any]:
        return await self._request("comm-bus", "GET", "/api/v1/bus/stats")

    async def publish_message(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("comm-bus", "POST", "/api/v1/bus/publish", json=data)
