"""Redis Streams event publisher."""

from __future__ import annotations

import re

import redis.asyncio as aioredis

from architect_common.logging import get_logger
from architect_events.schemas import EventEnvelope
from architect_events.serialization import serialize_event

logger = get_logger(component="architect_events.publisher")

_REDACT_RE = re.compile(r"(://:[^@]+@)")


def _redact_url(url: str) -> str:
    """Replace password in a Redis URL with '***'."""
    return _REDACT_RE.sub("://:***@", url)


class EventPublisher:
    """Publishes ``EventEnvelope`` instances to Redis Streams.

    Each event type maps to a dedicated stream named
    ``{stream_prefix}:{event.type}``, e.g. ``architect:task.created``.
    """

    def __init__(self, redis_url: str, stream_prefix: str = "architect") -> None:
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Create the underlying async Redis connection."""
        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )
        logger.info("EventPublisher connected", redis_url=_redact_url(self._redis_url))

    def _stream_name(self, event: EventEnvelope) -> str:
        return f"{self._stream_prefix}:{event.type}"

    async def publish(self, event: EventEnvelope) -> str:
        """Publish *event* to its Redis Stream and return the message ID.

        Raises ``RuntimeError`` if :meth:`connect` has not been called.
        """
        if self._redis is None:
            msg = "EventPublisher is not connected. Call connect() first."
            raise RuntimeError(msg)

        stream = self._stream_name(event)
        fields = serialize_event(event)

        message_id: bytes = await self._redis.xadd(
            stream,
            fields,  # type: ignore[arg-type]
            maxlen=10_000,
            approximate=True,
        )
        mid = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
        logger.debug("Published event", event_type=event.type, stream=stream, mid=mid)
        return mid

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.info("EventPublisher disconnected")
