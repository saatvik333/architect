"""Tests for agent_comm_bus.api.routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from agent_comm_bus.api.dependencies import get_message_bus
from agent_comm_bus.bus import MessageBus
from agent_comm_bus.models import AgentMessage, MessageType
from agent_comm_bus.service import create_app
from architect_common.types import AgentId


@pytest.fixture
def mock_bus() -> MessageBus:
    """Return a MessageBus with a mocked-out JetStream backend."""
    bus = MessageBus(nats_url="nats://test:4222")
    # Override internals so stats work without a real connection
    bus._js = AsyncMock()
    bus._js.publish = AsyncMock()
    return bus


@pytest.fixture
async def client(mock_bus: MessageBus) -> AsyncIterator[AsyncClient]:
    """Return an httpx AsyncClient wired to the FastAPI app with a mock bus."""
    app = create_app()
    app.dependency_overrides[get_message_bus] = lambda: mock_bus

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    async def test_root_health(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "agent-comm-bus"

    async def test_bus_health(self, client: AsyncClient) -> None:
        """GET /api/v1/bus/health returns healthy status."""
        resp = await client.get("/api/v1/bus/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


class TestBusStatsEndpoint:
    """Tests for the stats endpoint."""

    async def test_bus_stats(self, client: AsyncClient) -> None:
        """GET /api/v1/bus/stats returns zero stats for a fresh bus."""
        resp = await client.get("/api/v1/bus/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_published"] == 0
        assert data["total_received"] == 0


class TestPublishEndpoint:
    """Tests for the publish endpoint."""

    async def test_publish_message(
        self,
        client: AsyncClient,
        mock_bus: MessageBus,
    ) -> None:
        """POST /api/v1/bus/publish publishes a message and returns its ID."""
        msg = AgentMessage(
            id="msg-test00000001",
            sender=AgentId("agent-sender0001"),
            message_type=MessageType.TASK_ASSIGNED,
            payload={"foo": "bar"},
        )
        resp = await client.post(
            "/api/v1/bus/publish",
            json={
                "subject": "ARCHITECT.tasks",
                "message": msg.model_dump(mode="json"),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message_id"] == "msg-test00000001"
        assert data["subject"] == "ARCHITECT.tasks"
        assert data["status"] == "published"
