"""Async HTTP client for proxying requests to backend services."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from api_gateway.config import GatewayConfig

logger = logging.getLogger(__name__)

_SERVICE_URL_MAP = {
    "task-graph": "task_graph_url",
    "world-state": "world_state_url",
    "sandbox": "sandbox_url",
    "eval-engine": "eval_engine_url",
    "coding-agent": "coding_agent_url",
}


class ServiceClient:
    """HTTP client for proxying to backend ARCHITECT services."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Create the shared httpx async client."""
        self._client = httpx.AsyncClient(timeout=30.0)

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
        return getattr(self._config, attr)

    async def _request(
        self,
        service: str,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict:
        """Send an HTTP request to a backend service.

        Raises ``httpx.HTTPStatusError`` on non-2xx responses.
        """
        if self._client is None:
            msg = "ServiceClient not started — call startup() first"
            raise RuntimeError(msg)

        url = f"{self._base_url(service)}{path}"
        resp = await self._client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ── Typed methods ────────────────────────────────────────────────

    async def submit_task(self, data: dict) -> dict:
        return await self._request("task-graph", "POST", "/api/v1/tasks", json=data)

    async def get_task_status(self, task_id: str) -> dict:
        return await self._request("task-graph", "GET", f"/api/v1/tasks/{task_id}")

    async def get_task_logs(self, task_id: str, follow: bool = False) -> dict:
        return await self._request(
            "task-graph", "GET", f"/api/v1/tasks/{task_id}/logs", params={"follow": follow}
        )

    async def cancel_task(self, task_id: str, force: bool = False) -> dict:
        return await self._request(
            "task-graph", "POST", f"/api/v1/tasks/{task_id}/cancel", json={"force": force}
        )

    async def get_proposals(self, task_id: str) -> list[dict]:
        return await self._request(  # type: ignore[return-value]
            "world-state", "GET", f"/api/v1/tasks/{task_id}/proposals"
        )

    async def get_proposal(self, proposal_id: str) -> dict:
        return await self._request("world-state", "GET", f"/api/v1/proposals/{proposal_id}")

    async def submit_proposal(self, data: dict) -> dict:
        return await self._request("world-state", "POST", "/api/v1/state/proposals", json=data)

    async def get_world_state(self) -> dict:
        return await self._request("world-state", "GET", "/api/v1/state")

    async def get_service_health(self, service: str) -> dict:
        return await self._request(service, "GET", "/health")
