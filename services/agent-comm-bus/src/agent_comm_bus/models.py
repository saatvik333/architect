"""Pydantic domain models for the Agent Communication Bus."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from architect_common.types import AgentId, ArchitectBase, utcnow


class MessageType(StrEnum):
    """Types of messages exchanged between agents."""

    TASK_ASSIGNED = "task.assigned"
    TASK_COMPLETED = "task.completed"
    CONTEXT_REQUEST = "context.request"
    CONTEXT_RESPONSE = "context.response"
    STATE_PROPOSAL = "state.proposal"
    ESCALATION = "escalation"
    DISAGREEMENT = "disagreement"
    KNOWLEDGE_UPDATE = "knowledge.update"


class AgentMessage(ArchitectBase):
    """A typed message exchanged between ARCHITECT agents."""

    id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}")
    sender: AgentId
    recipient: AgentId | None = None  # None = broadcast
    message_type: MessageType
    payload: dict[str, object] = Field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    reply_to: str | None = None


class MessageStats(ArchitectBase):
    """Snapshot of message bus statistics."""

    total_published: int = 0
    total_received: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    dead_letter_count: int = 0
    active_subscriptions: int = 0


class DeadLetterEntry(ArchitectBase):
    """A message that failed processing and was sent to the dead-letter queue."""

    original_message: AgentMessage
    error: str
    failed_at: datetime = Field(default_factory=utcnow)
    retry_count: int = 0
