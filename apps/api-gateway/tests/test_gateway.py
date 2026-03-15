"""Tests for the ARCHITECT API Gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api_gateway import app
from api_gateway.service_client import ServiceClient


@pytest.fixture
def mock_client() -> AsyncMock:
    """A fully mocked ServiceClient."""
    return AsyncMock(spec=ServiceClient)


@pytest.fixture
def client(mock_client: AsyncMock) -> TestClient:
    """FastAPI TestClient with mocked ServiceClient."""
    with patch("api_gateway._client", mock_client):
        yield TestClient(app, raise_server_exceptions=False)


# ── Health ───────────────────────────────────────────────────────────


class TestHealth:
    def test_health_all_healthy(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert len(data["services"]) == 9

    def test_health_one_degraded(self, client: TestClient, mock_client: AsyncMock) -> None:
        call_count = 0

        async def side_effect(service: str) -> dict:
            nonlocal call_count
            call_count += 1
            if service == "sandbox":
                raise httpx.ConnectError("down")
            return {"status": "healthy"}

        mock_client.get_service_health.side_effect = side_effect
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["sandbox"] == "unhealthy"


# ── Tasks ────────────────────────────────────────────────────────────


class TestCreateTask:
    def test_create_task_success(self, client: TestClient, mock_client: AsyncMock) -> None:
        # Mock returns task-graph-engine's SubmitSpecResponse format
        mock_client.submit_task.return_value = {
            "task_count": 1,
            "task_ids": ["task-abc"],
            "execution_order": ["task-abc"],
            "validation_errors": [],
        }
        resp = client.post(
            "/api/v1/tasks",
            json={"name": "Test", "description": "A test task", "spec": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "task-abc"
        assert resp.json()["status"] == "accepted"

    def test_create_task_missing_fields(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks", json={"name": "only name"})
        assert resp.status_code == 422


class TestGetTask:
    def test_get_task_success(self, client: TestClient, mock_client: AsyncMock) -> None:
        # Mock returns task-graph-engine's TaskResponse format
        mock_client.get_task_status.return_value = {
            "id": "task-abc",
            "description": "Test",
            "status": "running",
            "type": "function",
            "priority": 5,
        }
        resp = client.get("/api/v1/tasks/task-abc")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert resp.json()["task_id"] == "task-abc"

    def test_get_task_backend_error(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_client.get_task_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=httpx.Request("GET", "/"), response=mock_resp
        )
        resp = client.get("/api/v1/tasks/nonexistent")
        assert resp.status_code == 404


class TestGetTaskLogs:
    def test_get_logs(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_task_logs.return_value = {
            "task_id": "task-abc",
            "entries": [
                {"timestamp": "2026-01-01T00:00:00Z", "level": "INFO", "message": "started"},
            ],
        }
        resp = client.get("/api/v1/tasks/task-abc/logs")
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 1


class TestCancelTask:
    def test_cancel(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.cancel_task.return_value = {"status": "cancelled"}
        resp = client.post("/api/v1/tasks/task-abc/cancel", json={"force": False})
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_no_body(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.cancel_task.return_value = {"status": "cancelled"}
        resp = client.post("/api/v1/tasks/task-abc/cancel")
        assert resp.status_code == 200


# ── Proposals ────────────────────────────────────────────────────────


class TestProposals:
    def test_list_proposals(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_proposals.return_value = [
            {"proposal_id": "p-1", "task_id": "task-abc", "agent_id": "a-1", "verdict": "pending"},
        ]
        resp = client.get("/api/v1/tasks/task-abc/proposals")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_proposal(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_proposal.return_value = {
            "proposal_id": "p-1",
            "task_id": "task-abc",
            "agent_id": "a-1",
            "mutations": [],
            "verdict": "approved",
        }
        resp = client.get("/api/v1/proposals/p-1")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "approved"

    def test_submit_proposal(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.submit_proposal.return_value = {"proposal_id": "p-new", "status": "pending"}
        resp = client.post(
            "/api/v1/state/proposals",
            json={
                "task_id": "task-abc",
                "agent_id": "agent-1",
                "mutations": [{"path": "x.y", "value": 1}],
            },
        )
        assert resp.status_code == 200


# ── World State ──────────────────────────────────────────────────────


class TestWorldState:
    def test_get_state(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_world_state.return_value = {"version": 3, "data": {"files": {}}}
        resp = client.get("/api/v1/state")
        assert resp.status_code == 200
        assert resp.json()["version"] == 3


# ── Error handling ───────────────────────────────────────────────────


class TestErrorHandling:
    def test_connect_error_returns_502(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_world_state.side_effect = httpx.ConnectError("Service down")
        resp = client.get("/api/v1/state")
        assert resp.status_code == 502
        assert "unavailable" in resp.json()["detail"].lower()
