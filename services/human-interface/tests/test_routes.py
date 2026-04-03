"""Tests for Human Interface API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from human_interface.api.dependencies import set_ws_manager
from human_interface.ws_manager import WebSocketManager


@pytest.fixture
def app():
    """Create a test app with DI wired (no lifespan to avoid Redis/DB)."""
    from fastapi import FastAPI

    from human_interface.api.routes import router

    ws_manager = WebSocketManager()
    set_ws_manager(ws_manager)

    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for the Human Interface HTTP API."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("healthy", "degraded")
        assert body["service"] == "human-interface"
        assert "uptime_seconds" in body

    async def test_get_activity_empty(self, client: AsyncClient) -> None:
        """GET /api/v1/activity should return an empty list initially."""
        response = await client.get("/api/v1/activity")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 0

    async def test_get_activity_with_limit(self, client: AsyncClient) -> None:
        """GET /api/v1/activity?limit=5 should accept a limit parameter."""
        response = await client.get("/api/v1/activity", params={"limit": 5})
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)


class TestRoutesWithMockDB:
    """Tests for routes using a mock session factory to verify endpoint behavior."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session that works as an async context manager."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def app_with_db(self, mock_session):
        """Create a test app with mocked DB session factory."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI

        from human_interface.api.dependencies import get_session_factory, set_ws_manager
        from human_interface.api.routes import router
        from human_interface.ws_manager import WebSocketManager

        ws_manager = WebSocketManager()
        set_ws_manager(ws_manager)

        captured_session = mock_session

        @asynccontextmanager
        async def _mock_factory():
            yield captured_session

        def _get_factory():
            return _mock_factory

        test_app = FastAPI()
        test_app.include_router(router)
        test_app.dependency_overrides[get_session_factory] = _get_factory

        return test_app

    @pytest.fixture
    async def db_client(self, app_with_db):
        """Return an async HTTP client wired to the app with mock DB."""
        transport = ASGITransport(app=app_with_db)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_post_escalation_creates_with_201(
        self, db_client: AsyncClient, mock_session
    ) -> None:
        """POST /api/v1/escalations should return 201 on success."""
        payload = {
            "source_agent_id": "agent-test",
            "source_task_id": "task-test",
            "summary": "Test escalation",
            "category": "architectural",
            "severity": "medium",
        }
        response = await db_client.post("/api/v1/escalations", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["summary"] == "Test escalation"
        assert body["status"] == "pending"
        assert body["source_agent_id"] == "agent-test"
        assert body["id"].startswith("esc-")

    async def test_get_escalations_returns_list(self, db_client: AsyncClient, mock_session) -> None:
        """GET /api/v1/escalations should return a list."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        response = await db_client.get("/api/v1/escalations")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)

    async def test_get_escalation_not_found_404(self, db_client: AsyncClient, mock_session) -> None:
        """GET /api/v1/escalations/{id} should return 404 for missing escalation."""
        mock_session.get = AsyncMock(return_value=None)

        response = await db_client.get("/api/v1/escalations/esc-nonexistent")
        assert response.status_code == 404

    async def test_post_approval_gate_creates_with_201(
        self, db_client: AsyncClient, mock_session
    ) -> None:
        """POST /api/v1/approval-gates should return 201 on success."""
        payload = {
            "action_type": "deploy",
            "resource_id": "res-test",
            "required_approvals": 2,
        }
        response = await db_client.post("/api/v1/approval-gates", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["action_type"] == "deploy"
        assert body["required_approvals"] == 2
        assert body["current_approvals"] == 0
        assert body["status"] == "pending"

    async def test_get_approval_gates_returns_list(
        self, db_client: AsyncClient, mock_session
    ) -> None:
        """GET /api/v1/approval-gates should return a list."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        response = await db_client.get("/api/v1/approval-gates")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)

    async def test_post_approval_gate_vote_not_found(
        self, db_client: AsyncClient, mock_session
    ) -> None:
        """POST /api/v1/approval-gates/{id}/vote should return 404 for missing gate."""
        mock_session.get = AsyncMock(return_value=None)

        payload = {
            "voter": "human-reviewer",
            "decision": "approve",
        }
        response = await db_client.post("/api/v1/approval-gates/gate-test/vote", json=payload)
        assert response.status_code == 404
