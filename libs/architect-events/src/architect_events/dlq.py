"""Dead-letter queue processor for failed events."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from architect_common.enums import EventType

logger = logging.getLogger(__name__)


class DeadLetterProcessor:
    """Manages the dead-letter queues for the event system.

    Provides reprocessing, purging, and inspection of failed events.
    """

    def __init__(self, redis_url: str, stream_prefix: str = "architect") -> None:
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Open the Redis connection."""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=False)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def _dlq_stream(self, event_type: EventType) -> str:
        return f"{self._stream_prefix}:dlq:{event_type}"

    def _origin_stream(self, event_type: EventType) -> str:
        return f"{self._stream_prefix}:{event_type}"

    async def count(self, event_type: EventType) -> int:
        """Return the number of messages in the DLQ for *event_type*."""
        assert self._redis is not None
        return await self._redis.xlen(self._dlq_stream(event_type))

    async def reprocess(self, event_type: EventType, count: int = 100) -> int:
        """Re-publish up to *count* DLQ messages back to the origin stream.

        Each message is removed from the DLQ after being re-published.
        Returns the number of messages reprocessed.
        """
        assert self._redis is not None
        dlq = self._dlq_stream(event_type)
        origin = self._origin_stream(event_type)

        messages = await self._redis.xrange(dlq, count=count)
        reprocessed = 0

        for mid, data in messages:
            # Strip DLQ metadata before re-publishing
            clean: dict[bytes, bytes] = {}
            for k, v in data.items():
                key = k if isinstance(k, bytes) else k.encode()
                if key in (b"original_stream", b"original_id", b"error"):
                    continue
                val = v if isinstance(v, bytes) else str(v).encode()
                clean[key] = val

            if clean:
                await self._redis.xadd(origin, clean)  # type: ignore[arg-type]
            await self._redis.xdel(dlq, mid)
            reprocessed += 1

        logger.info("Reprocessed %d messages from DLQ for %s", reprocessed, event_type)
        return reprocessed

    async def purge(self, event_type: EventType) -> None:
        """Delete the entire DLQ stream for *event_type*."""
        assert self._redis is not None
        dlq = self._dlq_stream(event_type)
        await self._redis.delete(dlq)
        logger.info("Purged DLQ stream %s", dlq)
