"""Tests for Multi-Model Router API routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from multi_model_router.service import create_app


@pytest.fixture
def app():
    """Create a fresh app instance for testing."""
    return create_app()


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Integration tests for the Multi-Model Router HTTP API."""

    async def test_post_route_returns_decision(self, client: AsyncClient) -> None:
        """POST /api/v1/route should return a valid routing decision."""
        response = await client.post(
            "/api/v1/route",
            json={
                "task_id": "task-test000001",
                "task_type": "fix_bug",
                "description": "Fix a null pointer in the parser",
                "token_estimate": 5000,
                "keywords": [],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "decision" in body
        assert body["decision"]["task_id"] == "task-test000001"
        assert body["decision"]["selected_tier"] in ("tier_1", "tier_2", "tier_3")
        assert "model_id" in body["decision"]

    async def test_get_stats_returns_stats(self, client: AsyncClient) -> None:
        """GET /api/v1/route/stats should return aggregate statistics."""
        # Make a request first to populate stats
        await client.post(
            "/api/v1/route",
            json={
                "task_id": "task-stats00001",
                "task_type": "write_test",
                "description": "Write tests",
            },
        )

        response = await client.get("/api/v1/route/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["total_requests"] >= 1
        assert "tier_distribution" in body
        assert "average_complexity" in body

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "multi-model-router"

    async def test_invalid_task_type_returns_422(self, client: AsyncClient) -> None:
        """POST /api/v1/route with an invalid task_type should return 422."""
        response = await client.post(
            "/api/v1/route",
            json={
                "task_id": "task-bad0000001",
                "task_type": "not_a_real_type",
                "description": "This should fail",
            },
        )
        assert response.status_code == 422
