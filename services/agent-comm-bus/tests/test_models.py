"""Tests for agent_comm_bus.models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agent_comm_bus.models import (
    AgentMessage,
    DeadLetterEntry,
    MessageType,
)
from architect_common.types import AgentId


class TestMessageType:
    """Tests for the MessageType enum."""

    def test_enum_values(self) -> None:
        """All expected message types exist with correct string values."""
        assert MessageType.TASK_ASSIGNED == "task.assigned"
        assert MessageType.TASK_COMPLETED == "task.completed"
        assert MessageType.CONTEXT_REQUEST == "context.request"
        assert MessageType.CONTEXT_RESPONSE == "context.response"
        assert MessageType.STATE_PROPOSAL == "state.proposal"
        assert MessageType.ESCALATION == "escalation"
        assert MessageType.DISAGREEMENT == "disagreement"
        assert MessageType.KNOWLEDGE_UPDATE == "knowledge.update"


class TestAgentMessage:
    """Tests for the AgentMessage model."""

    def test_frozen_behavior(self) -> None:
        """AgentMessage is frozen and cannot be mutated."""
        msg = AgentMessage(
            sender=AgentId("agent-s001"),
            message_type=MessageType.TASK_ASSIGNED,
        )
        with pytest.raises(ValidationError):
            msg.sender = AgentId("agent-s002")  # type: ignore[misc]

    def test_broadcast_recipient_none(self) -> None:
        """A broadcast message has recipient=None."""
        msg = AgentMessage(
            sender=AgentId("agent-s001"),
            message_type=MessageType.KNOWLEDGE_UPDATE,
        )
        assert msg.recipient is None

    def test_serialization_round_trip(self) -> None:
        """AgentMessage can be serialised to JSON and back without loss."""
        msg = AgentMessage(
            id="msg-roundtrip001",
            sender=AgentId("agent-s001"),
            recipient=AgentId("agent-r001"),
            message_type=MessageType.CONTEXT_REQUEST,
            payload={"key": "value"},
            correlation_id="corr-999",
        )
        json_str = msg.model_dump_json()
        restored = AgentMessage.model_validate(json.loads(json_str))

        assert restored.id == msg.id
        assert restored.sender == msg.sender
        assert restored.recipient == msg.recipient
        assert restored.message_type == msg.message_type
        assert restored.payload == msg.payload
        assert restored.correlation_id == msg.correlation_id

    def test_default_id_prefix(self) -> None:
        """Default message IDs start with 'msg-'."""
        msg = AgentMessage(
            sender=AgentId("agent-s001"),
            message_type=MessageType.ESCALATION,
        )
        assert msg.id.startswith("msg-")


class TestDeadLetterEntry:
    """Tests for the DeadLetterEntry model."""

    def test_contains_original_message(self) -> None:
        """DeadLetterEntry wraps the original AgentMessage."""
        msg = AgentMessage(
            sender=AgentId("agent-s001"),
            message_type=MessageType.TASK_ASSIGNED,
        )
        entry = DeadLetterEntry(original_message=msg, error="handler crashed")

        assert entry.original_message.id == msg.id
        assert entry.error == "handler crashed"
        assert entry.retry_count == 0
