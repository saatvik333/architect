"""Tests for Economic Governor API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from economic_governor.api.dependencies import (
    set_budget_tracker,
    set_efficiency_scorer,
    set_enforcer,
)
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer


@pytest.fixture
def test_config() -> EconomicGovernorConfig:
    """Config for route tests."""
    return EconomicGovernorConfig()


@pytest.fixture
def app(test_config: EconomicGovernorConfig):
    """Create a test app with DI wired to fresh instances."""
    mock_publisher = AsyncMock()
    mock_publisher.publish = AsyncMock()
    mock_publisher.connect = AsyncMock()
    mock_publisher.close = AsyncMock()

    tracker = BudgetTracker(test_config)
    scorer = EfficiencyScorer()
    enf = Enforcer(test_config, mock_publisher)

    set_budget_tracker(tracker)
    set_efficiency_scorer(scorer)
    set_enforcer(enf)

    # Import create_app here to avoid lifespan (which needs Redis).
    from fastapi import FastAPI

    from economic_governor.api.routes import router

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
    """Integration tests for the Economic Governor HTTP API."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "economic-governor"

    async def test_get_budget_status(self, client: AsyncClient) -> None:
        """GET /api/v1/budget/status should return a budget snapshot."""
        response = await client.get("/api/v1/budget/status")
        assert response.status_code == 200
        body = response.json()
        assert "allocated_tokens" in body
        assert "consumed_tokens" in body
        assert "enforcement_level" in body

    async def test_get_budget_phases(self, client: AsyncClient) -> None:
        """GET /api/v1/budget/phases should return per-phase breakdown."""
        response = await client.get("/api/v1/budget/phases")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 7  # One per BudgetPhase

    async def test_allocate_budget(self, client: AsyncClient) -> None:
        """POST /api/v1/budget/allocate should return a budget allocation."""
        response = await client.post(
            "/api/v1/budget/allocate",
            json={
                "project_id": "proj-test",
                "estimated_complexity": 0.6,
                "priority": 2,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["project_id"] == "proj-test"
        assert body["total_tokens"] > 0
        assert len(body["phase_allocations"]) == 7

    async def test_record_consumption(self, client: AsyncClient) -> None:
        """POST /api/v1/budget/record-consumption should return enforcement level."""
        response = await client.post(
            "/api/v1/budget/record-consumption",
            json={
                "agent_id": "agent-test",
                "tokens": 5000,
                "cost_usd": 0.005,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "enforcement_level" in body

    async def test_get_leaderboard_empty(self, client: AsyncClient) -> None:
        """GET /api/v1/efficiency/leaderboard should return empty board initially."""
        response = await client.get("/api/v1/efficiency/leaderboard")
        assert response.status_code == 200
        body = response.json()
        assert body["entries"] == []

    async def test_get_agent_efficiency_unknown(self, client: AsyncClient) -> None:
        """GET /api/v1/efficiency/agent/{id} should return default for unknown agent."""
        response = await client.get("/api/v1/efficiency/agent/agent-unknown")
        assert response.status_code == 200
        body = response.json()
        assert body["efficiency_score"] == 0.0

    async def test_get_enforcement_history_empty(self, client: AsyncClient) -> None:
        """GET /api/v1/enforcement/history should return empty list initially."""
        response = await client.get("/api/v1/enforcement/history")
        assert response.status_code == 200
        body = response.json()
        assert body == []

    async def test_get_current_enforcement_level(self, client: AsyncClient) -> None:
        """GET /api/v1/enforcement/current-level should return NONE initially."""
        response = await client.get("/api/v1/enforcement/current-level")
        assert response.status_code == 200
        body = response.json()
        assert body["level"] == "none"
        assert body["consumed_pct"] == 0.0
