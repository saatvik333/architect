"""Tests for X-Authenticated-User header identity derivation.

Verifies that resolve_escalation and cast_vote derive identity from the
X-Authenticated-User header, fall back to the body field, and reject
requests that provide neither (SEC-C3).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from human_interface.api.dependencies import get_session_factory, set_ws_manager
from human_interface.ws_manager import WebSocketManager


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def app_with_db(mock_session):
    """Create a test app with mocked DB session factory."""
    from fastapi import FastAPI

    from human_interface.api.routes import router

    ws_manager = WebSocketManager()
    set_ws_manager(ws_manager)

    @asynccontextmanager
    async def _mock_factory():
        yield mock_session

    def _get_factory():
        return _mock_factory

    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_session_factory] = _get_factory

    return test_app


@pytest.fixture
async def client(app_with_db):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── resolve_escalation identity tests ─────────────────────────────


class TestResolveEscalationIdentity:
    """Identity derivation for POST /api/v1/escalations/{id}/resolve."""

    @pytest.fixture(autouse=True)
    def _patch_repo(self, mock_session):
        """Patch the EscalationRepository to return a mock entity on resolve."""
        mock_entity = MagicMock()
        mock_entity.id = "esc-test-123"
        mock_entity.source_agent_id = None
        mock_entity.source_task_id = None
        mock_entity.summary = "Test"
        mock_entity.category = "architectural"
        mock_entity.severity = "medium"
        mock_entity.options = []
        mock_entity.recommended_option = None
        mock_entity.reasoning = None
        mock_entity.risk_if_wrong = None
        mock_entity.status = "resolved"
        mock_entity.resolved_by = "header-user"
        mock_entity.resolution = "Fixed"
        mock_entity.created_at = "2026-01-01T00:00:00Z"
        mock_entity.expires_at = None
        mock_entity.resolved_at = "2026-01-01T01:00:00Z"

        self._mock_entity = mock_entity
        self._resolve_mock = AsyncMock(return_value=mock_entity)

        patcher = patch(
            "human_interface.api.routes.EscalationRepository",
            return_value=MagicMock(resolve=self._resolve_mock),
        )
        patcher.start()
        yield
        patcher.stop()

    async def test_header_used_as_identity(self, client: AsyncClient) -> None:
        """X-Authenticated-User header should be used as resolved_by."""
        response = await client.post(
            "/api/v1/escalations/esc-test-123/resolve",
            json={"resolution": "Fixed"},
            headers={"X-Authenticated-User": "header-user"},
        )
        assert response.status_code == 200
        self._resolve_mock.assert_awaited_once()
        call_kwargs = self._resolve_mock.call_args[1]
        assert call_kwargs["resolved_by"] == "header-user"

    async def test_header_takes_precedence_over_body(self, client: AsyncClient) -> None:
        """X-Authenticated-User header should override body resolved_by."""
        response = await client.post(
            "/api/v1/escalations/esc-test-123/resolve",
            json={"resolution": "Fixed", "resolved_by": "body-user"},
            headers={"X-Authenticated-User": "header-user"},
        )
        assert response.status_code == 200
        call_kwargs = self._resolve_mock.call_args[1]
        assert call_kwargs["resolved_by"] == "header-user"

    async def test_body_fallback_when_no_header(self, client: AsyncClient) -> None:
        """Body resolved_by should be used when header is absent."""
        self._mock_entity.resolved_by = "body-user"
        response = await client.post(
            "/api/v1/escalations/esc-test-123/resolve",
            json={"resolution": "Fixed", "resolved_by": "body-user"},
        )
        assert response.status_code == 200
        call_kwargs = self._resolve_mock.call_args[1]
        assert call_kwargs["resolved_by"] == "body-user"

    async def test_401_when_no_identity(self, client: AsyncClient) -> None:
        """Should return 401 when neither header nor body provides identity."""
        response = await client.post(
            "/api/v1/escalations/esc-test-123/resolve",
            json={"resolution": "Fixed"},
        )
        assert response.status_code == 401
        assert "Identity required" in response.json()["detail"]


# ── cast_vote identity tests ──────────────────────────────────────


class TestCastVoteIdentity:
    """Identity derivation for POST /api/v1/approval-gates/{id}/vote."""

    @pytest.fixture(autouse=True)
    def _patch_repos(self, mock_session):
        """Patch gate and vote repos for vote tests."""
        mock_gate = MagicMock()
        mock_gate.id = "gate-test-123"
        mock_gate.action_type = "deploy"
        mock_gate.resource_id = None
        mock_gate.required_approvals = 1
        mock_gate.current_approvals = 0
        mock_gate.status = "pending"
        mock_gate.context = None
        mock_gate.created_at = "2026-01-01T00:00:00Z"
        mock_gate.expires_at = None
        mock_gate.resolved_at = None

        self._mock_gate = mock_gate
        self._gate_get_mock = AsyncMock(return_value=mock_gate)
        self._vote_get_mock = AsyncMock(return_value=[])
        self._vote_create_mock = AsyncMock()

        gate_repo_mock = MagicMock(
            get_by_id=self._gate_get_mock,
        )
        vote_repo_mock = MagicMock(
            get_by_gate=self._vote_get_mock,
            create=self._vote_create_mock,
        )

        gate_patcher = patch(
            "human_interface.api.routes.ApprovalGateRepository",
            return_value=gate_repo_mock,
        )
        vote_patcher = patch(
            "human_interface.api.routes.ApprovalVoteRepository",
            return_value=vote_repo_mock,
        )
        gate_patcher.start()
        vote_patcher.start()
        yield
        gate_patcher.stop()
        vote_patcher.stop()

    async def test_header_used_as_voter(self, client: AsyncClient) -> None:
        """X-Authenticated-User header should be used as voter."""
        response = await client.post(
            "/api/v1/approval-gates/gate-test-123/vote",
            json={"decision": "approve"},
            headers={"X-Authenticated-User": "header-voter"},
        )
        assert response.status_code == 200
        # Check the ApprovalVote was created with header identity.
        create_call = self._vote_create_mock.call_args[0][0]
        assert create_call.voter == "header-voter"

    async def test_header_takes_precedence_over_body(self, client: AsyncClient) -> None:
        """X-Authenticated-User header should override body voter."""
        response = await client.post(
            "/api/v1/approval-gates/gate-test-123/vote",
            json={"decision": "approve", "voter": "body-voter"},
            headers={"X-Authenticated-User": "header-voter"},
        )
        assert response.status_code == 200
        create_call = self._vote_create_mock.call_args[0][0]
        assert create_call.voter == "header-voter"

    async def test_body_fallback_when_no_header(self, client: AsyncClient) -> None:
        """Body voter should be used when header is absent."""
        response = await client.post(
            "/api/v1/approval-gates/gate-test-123/vote",
            json={"decision": "approve", "voter": "body-voter"},
        )
        assert response.status_code == 200
        create_call = self._vote_create_mock.call_args[0][0]
        assert create_call.voter == "body-voter"

    async def test_401_when_no_identity(self, client: AsyncClient) -> None:
        """Should return 401 when neither header nor body provides identity."""
        response = await client.post(
            "/api/v1/approval-gates/gate-test-123/vote",
            json={"decision": "approve"},
        )
        assert response.status_code == 401
        assert "Identity required" in response.json()["detail"]
