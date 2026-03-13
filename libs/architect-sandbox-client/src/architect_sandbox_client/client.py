"""HTTP client for the ARCHITECT execution sandbox service."""

from __future__ import annotations

from typing import Any

import httpx

from architect_sandbox_client.models import ExecutionRequest, ExecutionResult


class SandboxClient:
    """Async client for the Execution Sandbox service API.

    Usage::

        async with httpx.AsyncClient() as http:
            client = SandboxClient()
            result = await client.execute(request)
    """

    def __init__(self, base_url: str = "http://localhost:8002") -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(600.0))

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Submit an execution request and return the result.

        Sends the execution request to the sandbox service, which provisions
        a container, writes files, runs commands, and returns results.
        """
        response = await self._http.post(
            "/api/v1/execute",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return ExecutionResult.model_validate(response.json())

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Retrieve details about a sandbox session by ID."""
        response = await self._http.get(f"/api/v1/sessions/{session_id}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def health(self) -> bool:
        """Check whether the sandbox service is healthy."""
        try:
            response = await self._http.get("/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> SandboxClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
