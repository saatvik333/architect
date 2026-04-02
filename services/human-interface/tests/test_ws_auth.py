"""Tests for WebSocket authentication (fail-closed behaviour)."""

from __future__ import annotations

import os

# Ensure required env vars are set before importing app modules.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from human_interface.api.routes import router
from human_interface.ws_manager import WebSocketManager


@pytest.fixture
def _ws_manager() -> WebSocketManager:
    return WebSocketManager()


@pytest.fixture
def app(_ws_manager: WebSocketManager) -> FastAPI:
    """Create a minimal FastAPI app with the router mounted."""
    from human_interface.api.dependencies import get_ws_manager

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_ws_manager] = lambda: _ws_manager
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestWebSocketAuthFailClosed:
    """WebSocket endpoint must reject connections when ARCHITECT_WS_TOKEN is unset."""

    def test_rejected_when_env_var_unset(self, client: TestClient) -> None:
        """When ARCHITECT_WS_TOKEN is not set, all connections are rejected (fail-closed)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARCHITECT_WS_TOKEN", None)
            with (
                pytest.raises(WebSocketDisconnect) as exc_info,
                client.websocket_connect("/api/v1/ws?token=any-token"),
            ):
                pass  # pragma: no cover
            assert exc_info.value.code == 4003

    def test_rejected_when_no_token_param(self, client: TestClient) -> None:
        """When no token query parameter is provided, connection is rejected."""
        with (
            patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "secret-token"}),
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/api/v1/ws"),
        ):
            pass  # pragma: no cover
        assert exc_info.value.code == 4001

    def test_rejected_with_wrong_token(self, client: TestClient) -> None:
        """When the token does not match, connection is rejected."""
        with (
            patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "correct-token"}),
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/api/v1/ws?token=wrong-token"),
        ):
            pass  # pragma: no cover
        assert exc_info.value.code == 4001

    def test_accepted_with_correct_token(self, client: TestClient) -> None:
        """When the correct token is provided, connection is accepted."""
        with (
            patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "correct-token"}),
            client.websocket_connect("/api/v1/ws?token=correct-token") as ws,
        ):
            # Connection was accepted; close cleanly from the client side.
            ws.close()
