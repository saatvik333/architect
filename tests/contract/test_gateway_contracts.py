"""Contract tests verifying gateway-to-service response schemas.

These tests mock the upstream services and verify that the gateway
correctly transforms responses into its own schema. They do NOT
require running infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api_gateway import app, get_client, get_config
from api_gateway.service_client import ServiceClient


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock(spec=ServiceClient)


@pytest.fixture
def client(mock_client: AsyncMock) -> TestClient:
    app.dependency_overrides[get_client] = lambda: mock_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestTaskContract:
    """Verify the gateway transforms task-graph-engine responses correctly."""

    def test_create_task_response_schema(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.submit_task.return_value = {
            "task_count": 3,
            "task_ids": ["task-001", "task-002", "task-003"],
            "execution_order": ["task-001", "task-002", "task-003"],
            "validation_errors": [],
        }
        resp = client.post(
            "/api/v1/tasks", json={"name": "Test", "description": "desc", "spec": {}}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] == "accepted"

    def test_get_task_response_schema(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_task_status.return_value = {
            "id": "task-001",
            "description": "Implement auth",
            "status": "running",
            "type": "implement_feature",
            "priority": 5,
        }
        resp = client.get("/api/v1/tasks/task-001")
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert "name" in data
        assert "status" in data

    def test_list_tasks_response_is_list(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.list_tasks.return_value = {
            "tasks": [
                {"id": "t-1", "status": "pending", "type": "implement_feature"},
                {"id": "t-2", "status": "running", "type": "write_test"},
            ],
            "total": 2,
        }
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2


class TestProposalContract:
    """Verify the gateway transforms world-state-ledger responses correctly."""

    def test_get_proposal_response_schema(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_proposal.return_value = {
            "proposal_id": "p-001",
            "task_id": "task-001",
            "agent_id": "agent-001",
            "mutations": [{"path": "budget.consumed_tokens", "old_value": 0, "new_value": 100}],
            "verdict": "accepted",
        }
        resp = client.get("/api/v1/proposals/p-001")
        assert resp.status_code == 200
        data = resp.json()
        assert "proposal_id" in data
        assert "verdict" in data

    def test_get_world_state_response_schema(
        self, client: TestClient, mock_client: AsyncMock
    ) -> None:
        mock_client.get_world_state.return_value = {
            "version": 5,
            "data": {"budget": {"consumed_tokens": 1000}},
        }
        resp = client.get("/api/v1/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data


class TestHealthContract:
    """Verify the health endpoint aggregation contract."""

    def test_health_response_schema(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "services" in data
        assert isinstance(data["services"], dict)
        assert len(data["services"]) == 9

    def test_health_degraded_when_service_down(
        self, client: TestClient, mock_client: AsyncMock
    ) -> None:
        import httpx

        mock_client.get_service_health.side_effect = httpx.ConnectError("down")
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"
