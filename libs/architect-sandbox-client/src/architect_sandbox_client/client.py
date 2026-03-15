"""HTTP client for the ARCHITECT execution sandbox service."""

from __future__ import annotations

from typing import Any

import httpx

from architect_sandbox_client.models import ExecutionRequest, ExecutionResult


class SandboxClient:
    """Async client for the Execution Sandbox service API.

    Usage::

        async with SandboxClient() as client:
            result = await client.execute(request)
    """

    def __init__(self, base_url: str = "http://localhost:8002") -> None:
        self._base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the HTTP client on first use."""
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(600.0))
        return self._http

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Submit an execution request and return the result.

        Sends the execution request to the sandbox service, which provisions
        a container, writes files, runs commands, and returns results.
        """
        http = self._ensure_client()
        response = await http.post(
            "/api/v1/execute",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return ExecutionResult.model_validate(response.json())

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Retrieve details about a sandbox session by ID."""
        http = self._ensure_client()
        response = await http.get(f"/api/v1/sessions/{session_id}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def health(self) -> bool:
        """Check whether the sandbox service is healthy."""
        try:
            http = self._ensure_client()
            response = await http.get("/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> SandboxClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
