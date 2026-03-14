"""Tests for agent_comm_bus.dead_letter.DeadLetterHandler."""

from __future__ import annotations

from agent_comm_bus.dead_letter import DeadLetterHandler
from agent_comm_bus.models import AgentMessage


class TestDeadLetterHandler:
    """Tests for :class:`DeadLetterHandler`."""

    async def test_handle_failure_stores_entry(
        self,
        dead_letter_handler: DeadLetterHandler,
        sample_message: AgentMessage,
    ) -> None:
        """handle_failure() adds the message to the dead-letter queue."""
        await dead_letter_handler.handle_failure(sample_message, "timeout")

        assert dead_letter_handler.count == 1
        entries = await dead_letter_handler.get_entries()
        assert len(entries) == 1
        assert entries[0].original_message.id == sample_message.id
        assert entries[0].error == "timeout"

    async def test_get_entries_respects_limit(
        self,
        dead_letter_handler: DeadLetterHandler,
        sample_message: AgentMessage,
    ) -> None:
        """get_entries() returns at most *limit* entries."""
        for _ in range(5):
            await dead_letter_handler.handle_failure(sample_message, "err")

        entries = await dead_letter_handler.get_entries(limit=3)
        assert len(entries) == 3

    async def test_retry_removes_entry(
        self,
        dead_letter_handler: DeadLetterHandler,
        sample_message: AgentMessage,
    ) -> None:
        """retry() removes the entry and returns True if found."""
        await dead_letter_handler.handle_failure(sample_message, "err")

        assert dead_letter_handler.count == 1
        found = await dead_letter_handler.retry(sample_message.id)
        assert found is True
        assert dead_letter_handler.count == 0

    async def test_retry_returns_false_when_not_found(
        self,
        dead_letter_handler: DeadLetterHandler,
    ) -> None:
        """retry() returns False when the entry is not in the queue."""
        found = await dead_letter_handler.retry("msg-nonexistent1")
        assert found is False

    async def test_count_property(
        self,
        dead_letter_handler: DeadLetterHandler,
        sample_message: AgentMessage,
    ) -> None:
        """count returns the number of entries in the dead-letter queue."""
        assert dead_letter_handler.count == 0

        await dead_letter_handler.handle_failure(sample_message, "err1")
        assert dead_letter_handler.count == 1

        await dead_letter_handler.handle_failure(sample_message, "err2")
        assert dead_letter_handler.count == 2
