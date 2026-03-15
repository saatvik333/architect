"""Tests for World State Ledger API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from architect_common.enums import HealthStatus
from architect_common.errors import LedgerVersionNotFoundError
from world_state_ledger.api.dependencies import _get_event_log, _get_state_manager
from world_state_ledger.models import WorldState
from world_state_ledger.service import create_app


def _build_mock_state_manager() -> AsyncMock:
    """Build a mock StateManager with default return values."""
    manager = AsyncMock()
    manager.get_current.return_value = WorldState()
    manager.get_version.return_value = WorldState(version=1)
    manager.submit_proposal.return_value = "prop-abc123"
    manager.validate_and_commit.return_value = True
    return manager


def _build_mock_event_log() -> AsyncMock:
    """Build a mock EventLog with default return values."""
    event_log = AsyncMock()
    event_log.query.return_value = []
    return event_log


@pytest.fixture
def app():
    """Create a fresh app instance with mocked dependencies."""
    application = create_app()

    mock_manager = _build_mock_state_manager()
    mock_event_log = _build_mock_event_log()

    async def _override_manager() -> AsyncMock:
        return mock_manager

    async def _override_event_log() -> AsyncMock:
        return mock_event_log

    application.dependency_overrides[_get_state_manager] = _override_manager
    application.dependency_overrides[_get_event_log] = _override_event_log

    # Store mocks for test assertions.
    application.state.mock_manager = mock_manager
    application.state.mock_event_log = mock_event_log

    return application


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for World State Ledger API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == HealthStatus.HEALTHY
        assert data["service"] == "world-state-ledger"

    async def test_get_current_state(self, app, client: AsyncClient) -> None:
        """GET /state returns the current world state."""
        resp = await client.get("/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "build" in data
        assert "budget" in data
        app.state.mock_manager.get_current.assert_awaited_once()

    async def test_get_state_version(self, app, client: AsyncClient) -> None:
        """GET /state/{version} returns a specific historical version."""
        resp = await client.get("/state/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        app.state.mock_manager.get_version.assert_awaited_once_with(1)

    async def test_get_state_version_not_found(self, app, client: AsyncClient) -> None:
        """GET /state/{version} returns 404 for unknown version."""
        app.state.mock_manager.get_version.side_effect = LedgerVersionNotFoundError(
            "Version 999 not found"
        )
        resp = await client.get("/state/999")
        assert resp.status_code == 404

    async def test_submit_proposal(self, app, client: AsyncClient) -> None:
        """POST /proposals creates a proposal and returns its ID."""
        resp = await client.post(
            "/proposals",
            json={
                "agent_id": "agent-test0001",
                "task_id": "task-test0001",
                "mutations": [{"path": "budget.consumed_tokens", "old_value": 0, "new_value": 100}],
                "rationale": "Update budget tokens",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["proposal_id"] == "prop-abc123"
        app.state.mock_manager.submit_proposal.assert_awaited_once()

    async def test_commit_proposal(self, app, client: AsyncClient) -> None:
        """POST /proposals/{id}/commit validates and commits a proposal."""
        resp = await client.post("/proposals/prop-abc123/commit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal_id"] == "prop-abc123"
        assert data["accepted"] is True

    async def test_commit_proposal_not_found(self, app, client: AsyncClient) -> None:
        """POST /proposals/{id}/commit returns 404 for unknown proposal."""
        app.state.mock_manager.validate_and_commit.side_effect = LedgerVersionNotFoundError(
            "Proposal not found"
        )
        resp = await client.post("/proposals/prop-missing/commit")
        assert resp.status_code == 404

    async def test_query_events(self, app, client: AsyncClient) -> None:
        """GET /events returns event log entries."""
        app.state.mock_event_log.query.return_value = [
            {"id": "evt-001", "event_type": "task.created"}
        ]
        resp = await client.get("/events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["event_type"] == "task.created"

    async def test_query_events_with_filters(self, app, client: AsyncClient) -> None:
        """GET /events accepts filter query parameters."""
        resp = await client.get(
            "/events",
            params={
                "event_type": "task.created",
                "task_id": "task-test0001",
                "limit": 50,
                "offset": 10,
            },
        )
        assert resp.status_code == 200
        app.state.mock_event_log.query.assert_awaited_once()
