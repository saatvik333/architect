"""Tests for Coding Agent API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from architect_common.enums import HealthStatus, StatusEnum
from coding_agent.api.dependencies import get_agent_loop
from coding_agent.api.routes import _run_store
from coding_agent.models import AgentOutput, GeneratedFile
from coding_agent.service import create_app


def _build_mock_agent_loop() -> AsyncMock:
    """Build a mock CodingAgentLoop with a default successful output."""
    agent_loop = AsyncMock()
    agent_loop.execute.return_value = AgentOutput(
        task_id="task-test0001",
        agent_id="agent-test001",
        files=[
            GeneratedFile(path="src/hello.py", content='def greet(): return "hello"'),
        ],
        commit_message="Add greeting function",
        reasoning_summary="Generated a simple greeting function.",
        tokens_used=500,
        model_id="claude-sonnet-4-20250514",
    )
    return agent_loop


@pytest.fixture
def app():
    """Create a fresh app with a mocked agent loop."""
    application = create_app()

    mock_loop = _build_mock_agent_loop()

    async def _override_agent_loop():
        return mock_loop

    application.dependency_overrides[get_agent_loop] = _override_agent_loop
    application.state.mock_loop = mock_loop

    # Clear the in-memory run store between tests.
    _run_store.clear()

    return application


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for Coding Agent API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == HealthStatus.HEALTHY
        assert data["service"] == "coding-agent"

    async def test_execute_agent(self, app, client: AsyncClient) -> None:
        """POST /agent/execute runs the agent and returns output."""
        resp = await client.post(
            "/agent/execute",
            json={
                "task_id": "task-test0001",
                "spec_context": {
                    "title": "Add greeting",
                    "description": "Create a greeting function",
                },
                "codebase_context": {},
                "config": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-test0001"
        assert data["status"] == StatusEnum.COMPLETED
        assert data["files_generated"] == 1
        assert "agent_id" in data
        assert "output" in data
        app.state.mock_loop.execute.assert_awaited_once()

    async def test_execute_agent_stores_run(self, client: AsyncClient) -> None:
        """POST /agent/execute stores the run for later status retrieval."""
        resp = await client.post(
            "/agent/execute",
            json={
                "task_id": "task-store001",
                "spec_context": {},
                "codebase_context": {},
            },
        )
        agent_id = resp.json()["agent_id"]

        # The run should now be retrievable.
        status_resp = await client.get(f"/agent/{agent_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["agent_id"] == agent_id
        assert data["status"] == StatusEnum.COMPLETED

    async def test_get_agent_status_not_found(self, client: AsyncClient) -> None:
        """GET /agent/{agent_id} returns 404 for unknown agent."""
        resp = await client.get("/agent/agent-nonexistent")
        assert resp.status_code == 404
        assert "No agent run found" in resp.json()["detail"]

    async def test_execute_agent_missing_task_id(self, client: AsyncClient) -> None:
        """POST /agent/execute returns 422 when task_id is missing."""
        resp = await client.post("/agent/execute", json={})
        assert resp.status_code == 422

    async def test_execute_agent_with_minimal_body(self, app, client: AsyncClient) -> None:
        """POST /agent/execute works with only the required task_id field."""
        resp = await client.post(
            "/agent/execute",
            json={"task_id": "task-minimal01"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-minimal01"
        assert data["status"] == StatusEnum.COMPLETED
