"""Tests for the knowledge memory event handler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EventType, ObservationType
from architect_common.types import AgentId, TaskId
from architect_events.schemas import EventEnvelope
from knowledge_memory.event_handler import KnowledgeEventHandler
from knowledge_memory.knowledge_store import KnowledgeStore


class TestKnowledgeEventHandler:
    """Tests for KnowledgeEventHandler operations."""

    @pytest.fixture
    def mock_store(self) -> AsyncMock:
        """Create a mock KnowledgeStore."""
        return AsyncMock(spec=KnowledgeStore)

    @pytest.fixture
    def handler(self, mock_store: AsyncMock) -> KnowledgeEventHandler:
        """Create a KnowledgeEventHandler with a mocked store."""
        return KnowledgeEventHandler(knowledge_store=mock_store)

    def _make_envelope(self, event_type: EventType, payload: dict) -> EventEnvelope:
        """Helper to create an EventEnvelope."""
        return EventEnvelope(type=event_type, payload=payload, correlation_id="corr-001")

    # ── handle_task_completed ────────────────────────────────────────

    async def test_handle_task_completed_creates_observation(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_completed creates observation with correct fields."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"task_id": "task-001", "agent_id": "agent-001", "verdict": "pass"},
        )

        await handler.handle_task_completed(envelope)

        mock_store.store_observation.assert_called_once()
        call_kwargs = mock_store.store_observation.call_args.kwargs
        assert call_kwargs["task_id"] == TaskId("task-001")
        assert call_kwargs["agent_id"] == AgentId("agent-001")
        assert call_kwargs["observation_type"] == ObservationType.SUCCESS
        assert "task-001" in call_kwargs["description"]
        assert "pass" in call_kwargs["description"]
        assert call_kwargs["outcome"] == "pass"
        assert call_kwargs["context"]["verdict"] == "pass"
        assert call_kwargs["context"]["correlation_id"] == "corr-001"

    async def test_handle_task_completed_default_verdict(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_completed with empty verdict still creates observation."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"task_id": "task-002", "agent_id": "agent-002"},
        )

        await handler.handle_task_completed(envelope)

        mock_store.store_observation.assert_called_once()

    # ── handle_task_failed ───────────────────────────────────────────

    async def test_handle_task_failed_creates_observation(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_failed creates observation with correct fields."""
        envelope = self._make_envelope(
            EventType.TASK_FAILED,
            {
                "task_id": "task-003",
                "agent_id": "agent-003",
                "error_message": "Timeout exceeded",
            },
        )

        await handler.handle_task_failed(envelope)

        mock_store.store_observation.assert_called_once()
        call_kwargs = mock_store.store_observation.call_args.kwargs
        assert call_kwargs["task_id"] == TaskId("task-003")
        assert call_kwargs["agent_id"] == AgentId("agent-003")
        assert call_kwargs["observation_type"] == ObservationType.FAILURE
        assert "Timeout exceeded" in call_kwargs["description"]
        assert call_kwargs["outcome"] == "failed"
        assert call_kwargs["context"]["error_message"] == "Timeout exceeded"

    # ── Validation ───────────────────────────────────────────────────

    async def test_handle_task_completed_missing_optional_fields(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_completed with only verdict still creates observation (fields have defaults)."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"verdict": "pass"},  # task_id and agent_id default to ""
        )

        await handler.handle_task_completed(envelope)

        mock_store.store_observation.assert_called_once()

    async def test_handle_task_completed_invalid_payload(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_completed with invalid types rejects the event."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"tokens_consumed": -1},  # violates ge=0 constraint
        )

        await handler.handle_task_completed(envelope)

        mock_store.store_observation.assert_not_called()

    async def test_handle_task_failed_missing_fields(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_failed with missing payload fields rejects."""
        envelope = self._make_envelope(
            EventType.TASK_FAILED,
            {"error_message": "bad"},  # missing task_id and agent_id
        )

        await handler.handle_task_failed(envelope)

        mock_store.store_observation.assert_not_called()

    async def test_handle_task_completed_calls_store_correctly(
        self, handler: KnowledgeEventHandler, mock_store: AsyncMock
    ) -> None:
        """handle_task_completed with valid payload calls store methods correctly."""
        envelope = self._make_envelope(
            EventType.TASK_COMPLETED,
            {"task_id": "task-010", "agent_id": "agent-010", "verdict": "pass"},
        )

        await handler.handle_task_completed(envelope)

        mock_store.store_observation.assert_called_once()
        call_kwargs = mock_store.store_observation.call_args.kwargs
        # Ensure the obs_id is a proper KnowledgeId
        assert str(call_kwargs["obs_id"]).startswith("know-")
