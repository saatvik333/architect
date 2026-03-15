"""Tests for Execution Sandbox API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from architect_common.enums import HealthStatus, SandboxStatus
from architect_common.errors import SandboxError, SandboxSecurityError, SandboxTimeoutError
from execution_sandbox.api.dependencies import get_executor
from execution_sandbox.models import SandboxSession
from execution_sandbox.service import create_app


def _make_session_mock() -> MagicMock:
    """Return a mock SandboxSession with sensible defaults."""
    session = MagicMock(spec=SandboxSession)
    session.id = "sbx-test000001"
    session.status = SandboxStatus.READY
    session.container_id = "ctr-abc123"
    session.audit_log = []
    session.exit_code = None
    return session


def _build_mock_executor() -> AsyncMock:
    """Build a mock DockerExecutor with default return values."""
    executor = AsyncMock()
    executor._sessions = {}

    session = _make_session_mock()

    # create() is async, returns a SandboxSession.
    executor.create.return_value = session

    # execute_command() is async, returns (exit_code, stdout, stderr).
    executor.execute_command.return_value = (0, "hello\n", "")

    # write_files() is async, no-op.
    executor.write_files.return_value = None

    # read_files() is async, returns a dict of path -> content.
    executor.read_files.return_value = {"main.py": "print('hello')"}

    # destroy() is async, no-op.
    executor.destroy.return_value = None

    # get_session() is SYNC — use a plain MagicMock to avoid returning a coroutine.
    executor.get_session = MagicMock(return_value=session)

    return executor


@pytest.fixture
def app():
    """Create a fresh app with a mocked executor."""
    application = create_app()

    mock_executor = _build_mock_executor()
    application.dependency_overrides[get_executor] = lambda: mock_executor

    # Store the mock for test assertions.
    application.state.mock_executor = mock_executor

    return application


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _sandbox_spec_payload() -> dict:
    """Return a valid CreateSandboxRequest JSON payload."""
    return {
        "spec": {
            "task_id": "task-test0001",
            "agent_id": "agent-test001",
            "base_image": "architect-sandbox:latest",
        }
    }


class TestRoutes:
    """Tests for Execution Sandbox API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == HealthStatus.HEALTHY

    async def test_create_sandbox(self, app, client: AsyncClient) -> None:
        """POST /sandbox/create provisions a new sandbox."""
        resp = await client.post("/sandbox/create", json=_sandbox_spec_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "sbx-test000001"
        assert data["status"] == SandboxStatus.READY
        app.state.mock_executor.create.assert_awaited_once()

    async def test_create_sandbox_error(self, app, client: AsyncClient) -> None:
        """POST /sandbox/create returns 500 on SandboxError."""
        app.state.mock_executor.create.side_effect = SandboxError("Docker unavailable")
        resp = await client.post("/sandbox/create", json=_sandbox_spec_payload())
        assert resp.status_code == 500
        assert "Docker unavailable" in resp.json()["detail"]

    async def test_exec_command(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/exec executes a command inside a sandbox."""
        resp = await client.post(
            "/sandbox/sbx-test000001/exec",
            json={"command": "echo hello", "timeout": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exit_code"] == 0
        assert data["stdout"] == "hello\n"
        assert data["stderr"] == ""

    async def test_exec_command_security_error(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/exec returns 403 on security violation."""
        app.state.mock_executor.execute_command.side_effect = SandboxSecurityError(
            "Blocked command"
        )
        resp = await client.post(
            "/sandbox/sbx-test000001/exec",
            json={"command": "rm -rf /"},
        )
        assert resp.status_code == 403

    async def test_exec_command_timeout(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/exec returns 408 on timeout."""
        app.state.mock_executor.execute_command.side_effect = SandboxTimeoutError(
            "Command timed out"
        )
        resp = await client.post(
            "/sandbox/sbx-test000001/exec",
            json={"command": "sleep 9999"},
        )
        assert resp.status_code == 408

    async def test_exec_command_not_found(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/exec returns 404 for unknown session."""
        app.state.mock_executor.execute_command.side_effect = SandboxError("Session not found")
        resp = await client.post(
            "/sandbox/sbx-missing/exec",
            json={"command": "echo hi"},
        )
        assert resp.status_code == 404

    async def test_write_files(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/files writes files into a sandbox."""
        resp = await client.post(
            "/sandbox/sbx-test000001/files",
            json={"files": {"main.py": "print('hello')"}},
        )
        assert resp.status_code == 204
        app.state.mock_executor.write_files.assert_awaited_once()

    async def test_write_files_security_error(self, app, client: AsyncClient) -> None:
        """POST /sandbox/{id}/files returns 403 on security violation."""
        app.state.mock_executor.write_files.side_effect = SandboxSecurityError(
            "Path traversal blocked"
        )
        resp = await client.post(
            "/sandbox/sbx-test000001/files",
            json={"files": {"../../etc/passwd": "hacked"}},
        )
        assert resp.status_code == 403

    async def test_get_session(self, app, client: AsyncClient) -> None:
        """GET /sandbox/{id} returns session state."""
        resp = await client.get("/sandbox/sbx-test000001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "sbx-test000001"
        assert data["status"] == SandboxStatus.READY

    async def test_get_session_not_found(self, app, client: AsyncClient) -> None:
        """GET /sandbox/{id} returns 404 for unknown session."""
        app.state.mock_executor.get_session.return_value = None
        resp = await client.get("/sandbox/sbx-missing")
        assert resp.status_code == 404

    async def test_destroy_sandbox(self, app, client: AsyncClient) -> None:
        """DELETE /sandbox/{id} destroys a sandbox."""
        resp = await client.delete("/sandbox/sbx-test000001")
        assert resp.status_code == 204
        app.state.mock_executor.destroy.assert_awaited_once_with("sbx-test000001")

    async def test_destroy_sandbox_not_found(self, app, client: AsyncClient) -> None:
        """DELETE /sandbox/{id} returns 404 for unknown session."""
        app.state.mock_executor.destroy.side_effect = SandboxError("Session not found")
        resp = await client.delete("/sandbox/sbx-missing")
        assert resp.status_code == 404
