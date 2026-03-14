"""FastAPI dependency injection for the Agent Communication Bus."""

from __future__ import annotations

from functools import lru_cache

from agent_comm_bus.bus import MessageBus
from agent_comm_bus.config import AgentCommBusConfig
from agent_comm_bus.dead_letter import DeadLetterHandler


@lru_cache(maxsize=1)
def get_config() -> AgentCommBusConfig:
    """Return the cached service configuration."""
    return AgentCommBusConfig()


_message_bus: MessageBus | None = None
_dead_letter_handler: DeadLetterHandler | None = None


def get_message_bus() -> MessageBus:
    """Return the shared :class:`MessageBus` singleton (lazy init, not connected)."""
    global _message_bus
    if _message_bus is None:
        config = get_config()
        _message_bus = MessageBus(
            nats_url=config.nats_url,
            stream_name=config.stream_name,
        )
    return _message_bus


def get_dead_letter_handler() -> DeadLetterHandler:
    """Return the shared :class:`DeadLetterHandler` singleton."""
    global _dead_letter_handler
    if _dead_letter_handler is None:
        config = get_config()
        _dead_letter_handler = DeadLetterHandler(max_retries=config.max_retries)
    return _dead_letter_handler


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _message_bus, _dead_letter_handler
    if _message_bus is not None:
        await _message_bus.close()
        _message_bus = None
    _dead_letter_handler = None
