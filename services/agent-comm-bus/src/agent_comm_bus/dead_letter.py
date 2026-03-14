"""Dead-letter queue handler for failed messages."""

from __future__ import annotations

from agent_comm_bus.models import AgentMessage, DeadLetterEntry
from architect_common.logging import get_logger

logger = get_logger(component="dead-letter")


class DeadLetterHandler:
    """In-memory dead-letter queue for messages that failed processing.

    In production this would be backed by a persistent store; the in-memory
    implementation is sufficient for the initial Phase 1 build.
    """

    def __init__(self, max_retries: int = 3) -> None:
        self._entries: list[DeadLetterEntry] = []
        self._max_retries = max_retries

    async def handle_failure(self, message: AgentMessage, error: str) -> None:
        """Record a failed message in the dead-letter queue."""
        entry = DeadLetterEntry(original_message=message, error=error)
        self._entries.append(entry)
        logger.warning(
            "message sent to dead-letter queue",
            message_id=message.id,
            error=error,
        )

    async def get_entries(self, limit: int = 100) -> list[DeadLetterEntry]:
        """Return the most recent dead-letter entries, up to *limit*."""
        return self._entries[-limit:]

    async def retry(self, entry_id: str) -> bool:
        """Remove an entry by its original message id, returning True if found."""
        for i, entry in enumerate(self._entries):
            if entry.original_message.id == entry_id:
                self._entries.pop(i)
                logger.info("retried dead-letter entry", message_id=entry_id)
                return True
        return False

    @property
    def count(self) -> int:
        """Number of entries currently in the dead-letter queue."""
        return len(self._entries)
