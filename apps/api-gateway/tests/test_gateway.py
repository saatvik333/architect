"""Tests for the ARCHITECT API Gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from api_gateway import RateLimitMiddleware, app, get_client, get_config
from api_gateway.config import GatewayConfig
from api_gateway.service_client import ServiceClient

_TEST_API_KEY = "test-key-abcdef1234567890abcdef1234567890"


@pytest.fixture
def mock_client() -> AsyncMock:
    """A fully mocked ServiceClient."""
    return AsyncMock(spec=ServiceClient)


@pytest.fixture
def _auth_config(monkeypatch: pytest.MonkeyPatch) -> GatewayConfig:
    """Override gateway config with auth enabled and a known key."""
    monkeypatch.setenv("ARCHITECT_GATEWAY_API_KEYS_RAW", _TEST_API_KEY)
    monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "true")
    get_config.cache_clear()
    cfg = get_config()
    yield cfg  # type: ignore[misc]
    get_config.cache_clear()


@pytest.fixture
def _noauth_config(monkeypatch: pytest.MonkeyPatch) -> GatewayConfig:
    """Override gateway config with auth disabled for route-logic tests."""
    monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
    monkeypatch.delenv("ARCHITECT_GATEWAY_API_KEYS_RAW", raising=False)
    get_config.cache_clear()
    cfg = get_config()
    yield cfg  # type: ignore[misc]
    get_config.cache_clear()


@pytest.fixture
def client(mock_client: AsyncMock, _noauth_config: GatewayConfig) -> TestClient:
    """FastAPI TestClient with mocked ServiceClient and auth disabled."""
    app.dependency_overrides[get_client] = lambda: mock_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(mock_client: AsyncMock, _auth_config: GatewayConfig) -> TestClient:
    """FastAPI TestClient with auth enabled and a known API key."""
    app.dependency_overrides[get_client] = lambda: mock_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ── Authentication ──────────────────────────────────────────────────


class TestAuthentication:
    def test_missing_auth_header_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/api/v1/tasks")
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    def test_invalid_key_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.get(
            "/api/v1/tasks",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_valid_key_passes(self, auth_client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.list_tasks.return_value = {"tasks": [], "total": 0}
        resp = auth_client.get(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
        )
        assert resp.status_code == 200

    def test_health_no_auth_required(self, auth_client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = auth_client.get("/health")
        assert resp.status_code == 200

    def test_api_v1_health_no_auth_required(
        self, auth_client: TestClient, mock_client: AsyncMock
    ) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = auth_client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_options_no_auth_required(self, auth_client: TestClient) -> None:
        resp = auth_client.options("/api/v1/tasks")
        # CORS preflight should not be blocked by auth
        assert resp.status_code != 401

    def test_auth_disabled_allows_all(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.list_tasks.return_value = {"tasks": [], "total": 0}
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200

    def test_malformed_auth_header_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.get(
            "/api/v1/tasks",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401


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


# ── Security Headers ─────────────────────────────────────────────────


class TestSecurityHeaders:
    def test_security_headers_present(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = client.get("/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_no_hsts_in_dev(self, client: TestClient, mock_client: AsyncMock) -> None:
        mock_client.get_service_health.return_value = {"status": "healthy"}
        resp = client.get("/health")
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_in_production(
        self,
        mock_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
        monkeypatch.setenv("ARCHITECT_GATEWAY_ENVIRONMENT", "production")
        get_config.cache_clear()
        try:
            c = TestClient(app, raise_server_exceptions=False)
            app.dependency_overrides[get_client] = lambda: mock_client
            mock_client.get_service_health.return_value = {"status": "healthy"}
            resp = c.get("/health")
            assert resp.headers.get("Strict-Transport-Security") == "max-age=31536000"
        finally:
            get_config.cache_clear()
            app.dependency_overrides.clear()


# ── Rate Limiting ────────────────────────────────────────────────────


class TestRateLimiting:
    def test_rate_limit_exceeded(
        self,
        mock_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        RateLimitMiddleware.reset()
        monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
        monkeypatch.setenv("ARCHITECT_GATEWAY_RATE_LIMIT_PER_MINUTE", "3")
        get_config.cache_clear()
        try:
            c = TestClient(app, raise_server_exceptions=False)
            app.dependency_overrides[get_client] = lambda: mock_client
            mock_client.list_tasks.return_value = {"tasks": [], "total": 0}

            for _ in range(3):
                resp = c.get("/api/v1/tasks")
                assert resp.status_code == 200

            resp = c.get("/api/v1/tasks")
            assert resp.status_code == 429
            assert "Retry-After" in resp.headers
        finally:
            RateLimitMiddleware.reset()
            get_config.cache_clear()
            app.dependency_overrides.clear()

    def test_health_exempt_from_rate_limit(
        self,
        mock_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        RateLimitMiddleware.reset()
        monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
        monkeypatch.setenv("ARCHITECT_GATEWAY_RATE_LIMIT_PER_MINUTE", "2")
        get_config.cache_clear()
        try:
            c = TestClient(app, raise_server_exceptions=False)
            app.dependency_overrides[get_client] = lambda: mock_client
            mock_client.get_service_health.return_value = {"status": "healthy"}

            for _ in range(10):
                resp = c.get("/health")
                assert resp.status_code == 200
        finally:
            RateLimitMiddleware.reset()
            get_config.cache_clear()
            app.dependency_overrides.clear()


# ── Request Size Limit ───────────────────────────────────────────────


class TestRequestSizeLimit:
    def test_oversized_request_returns_413(
        self,
        mock_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "false")
        monkeypatch.setenv("ARCHITECT_GATEWAY_MAX_REQUEST_BODY_BYTES", "100")
        get_config.cache_clear()
        try:
            c = TestClient(app, raise_server_exceptions=False)
            app.dependency_overrides[get_client] = lambda: mock_client
            resp = c.post(
                "/api/v1/tasks",
                json={"name": "x" * 200, "description": "y" * 200},
            )
            assert resp.status_code == 413
        finally:
            get_config.cache_clear()
            app.dependency_overrides.clear()
