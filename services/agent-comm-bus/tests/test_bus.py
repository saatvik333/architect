"""Tests for agent_comm_bus.bus.MessageBus."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_comm_bus.bus import MessageBus, MessageBusError, MessageTimeoutError
from agent_comm_bus.models import AgentMessage, MessageType
from architect_common.types import AgentId


class TestMessageBusConnect:
    """Tests for MessageBus connection lifecycle."""

    async def test_connect_calls_nats(self) -> None:
        """connect() establishes a NATS connection and JetStream context."""
        mock_nc = MagicMock()
        mock_nc.is_closed = False
        mock_nc.close = AsyncMock()

        mock_js = MagicMock()
        mock_js.find_stream_info_by_subject = AsyncMock()
        mock_js.add_stream = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        bus = MessageBus(nats_url="nats://test:4222")
        with patch("agent_comm_bus.bus.nats.connect", new_callable=AsyncMock, return_value=mock_nc) as mock_connect:
            await bus.connect()

        mock_connect.assert_called_once_with("nats://test:4222")
        mock_nc.jetstream.assert_called_once()

    async def test_close_drains_connection(
        self,
        message_bus: MessageBus,
        mock_nats_client: MagicMock,
    ) -> None:
        """close() closes the NATS connection."""
        await message_bus.close()
        mock_nats_client.close.assert_called_once()


class TestMessageBusPublish:
    """Tests for MessageBus.publish."""

    async def test_publish_serializes_and_sends(
        self,
        message_bus: MessageBus,
        mock_nats_client: MagicMock,
        sample_message: AgentMessage,
    ) -> None:
        """publish() serializes the message to JSON and calls js.publish."""
        await message_bus.publish("ARCHITECT.tasks", sample_message)

        js = mock_nats_client.jetstream()
        js.publish.assert_called_once()
        call_args = js.publish.call_args
        assert call_args[0][0] == "ARCHITECT.tasks"

        # Verify the serialized data is valid JSON containing the message
        data = call_args[0][1]
        parsed = json.loads(data)
        assert parsed["id"] == sample_message.id

    async def test_publish_updates_stats(
        self,
        message_bus: MessageBus,
        sample_message: AgentMessage,
    ) -> None:
        """publish() increments the total_published stat."""
        await message_bus.publish("ARCHITECT.tasks", sample_message)

        stats = message_bus.stats
        assert stats.total_published == 1
        assert stats.by_type.get("task.assigned") == 1

    async def test_publish_not_connected_raises(
        self,
        sample_message: AgentMessage,
    ) -> None:
        """publish() raises MessageBusError when not connected."""
        bus = MessageBus()
        with pytest.raises(MessageBusError, match="Not connected"):
            await bus.publish("ARCHITECT.tasks", sample_message)


class TestMessageBusSubscribe:
    """Tests for MessageBus.subscribe."""

    async def test_subscribe_registers_handler(
        self,
        message_bus: MessageBus,
        mock_nats_client: MagicMock,
    ) -> None:
        """subscribe() registers a callback via JetStream."""
        handler = AsyncMock()
        await message_bus.subscribe("ARCHITECT.tasks", handler)

        js = mock_nats_client.jetstream()
        js.subscribe.assert_called_once()

    async def test_subscribe_updates_active_count(
        self,
        message_bus: MessageBus,
    ) -> None:
        """subscribe() increments active_subscriptions in stats."""
        handler = AsyncMock()
        await message_bus.subscribe("ARCHITECT.tasks", handler)

        stats = message_bus.stats
        assert stats.active_subscriptions == 1


class TestMessageBusRequest:
    """Tests for MessageBus.request (request-reply pattern)."""

    async def test_request_timeout_raises(
        self,
        message_bus: MessageBus,
        mock_nats_client: MagicMock,
        sample_message: AgentMessage,
    ) -> None:
        """request() raises MessageTimeoutError on NATS timeout."""
        import nats.errors

        mock_nats_client.request.side_effect = nats.errors.TimeoutError()

        with pytest.raises(MessageTimeoutError, match="timed out"):
            await message_bus.request("ARCHITECT.rpc", sample_message, timeout=1.0)

    async def test_request_returns_response(
        self,
        message_bus: MessageBus,
        mock_nats_client: MagicMock,
        sample_message: AgentMessage,
    ) -> None:
        """request() returns a deserialized AgentMessage from the reply."""
        reply_msg = AgentMessage(
            id="msg-reply0000001",
            sender=AgentId("agent-responder1"),
            message_type=MessageType.CONTEXT_RESPONSE,
            payload={"answer": "42"},
        )
        mock_reply = MagicMock()
        mock_reply.data = reply_msg.model_dump_json().encode()
        mock_nats_client.request.return_value = mock_reply

        result = await message_bus.request("ARCHITECT.rpc", sample_message, timeout=5.0)

        assert result.id == "msg-reply0000001"
        assert result.message_type == MessageType.CONTEXT_RESPONSE
        assert result.payload == {"answer": "42"}


class TestMessageBusStats:
    """Tests for MessageBus stats property."""

    async def test_stats_initially_zero(self) -> None:
        """A fresh MessageBus has all-zero stats."""
        bus = MessageBus()
        stats = bus.stats
        assert stats.total_published == 0
        assert stats.total_received == 0
        assert stats.by_type == {}
        assert stats.active_subscriptions == 0
