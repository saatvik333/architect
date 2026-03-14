"""Shared pytest fixtures for agent-comm-bus tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_comm_bus.bus import MessageBus
from agent_comm_bus.dead_letter import DeadLetterHandler
from agent_comm_bus.models import AgentMessage, MessageType
from architect_common.types import AgentId


@pytest.fixture
def sample_message() -> AgentMessage:
    """Return a sample agent message for testing."""
    return AgentMessage(
        id="msg-test00000001",
        sender=AgentId("agent-sender0001"),
        recipient=AgentId("agent-recv000001"),
        message_type=MessageType.TASK_ASSIGNED,
        payload={"task": "implement-feature"},
        correlation_id="corr-001",
    )


@pytest.fixture
def broadcast_message() -> AgentMessage:
    """Return a broadcast agent message (no recipient)."""
    return AgentMessage(
        id="msg-broadcast001",
        sender=AgentId("agent-sender0001"),
        recipient=None,
        message_type=MessageType.KNOWLEDGE_UPDATE,
        payload={"key": "value"},
    )


@pytest.fixture
def mock_nats_client() -> MagicMock:
    """Return a mock NATS client with JetStream support.

    ``jetstream()`` is a sync method in the real NATS client, so we use
    MagicMock for the top-level client and keep async methods as AsyncMock.
    """
    nc = MagicMock()
    nc.is_closed = False
    nc.close = AsyncMock()
    nc.request = AsyncMock()

    js = MagicMock()
    js.publish = AsyncMock()
    js.subscribe = AsyncMock(return_value=AsyncMock())
    js.find_stream_info_by_subject = AsyncMock()
    js.add_stream = AsyncMock()

    nc.jetstream.return_value = js

    return nc


@pytest.fixture
async def message_bus(mock_nats_client: MagicMock) -> MessageBus:
    """Return a MessageBus connected with a mock NATS client."""
    bus = MessageBus(nats_url="nats://test:4222", stream_name="TEST")
    with patch("agent_comm_bus.bus.nats.connect", return_value=mock_nats_client):
        await bus.connect()
    return bus


@pytest.fixture
def dead_letter_handler() -> DeadLetterHandler:
    """Return a fresh DeadLetterHandler."""
    return DeadLetterHandler(max_retries=3)
