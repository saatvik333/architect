"""Tests for Human Interface API routes."""

from __future__ import annotations

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
        assert body["status"] == "healthy"
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
