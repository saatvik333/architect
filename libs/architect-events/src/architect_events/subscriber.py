"""Redis Streams consumer-group event subscriber."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis

from architect_common.enums import EventType
from architect_events.schemas import EventEnvelope
from architect_events.serialization import deserialize_event

logger = logging.getLogger(__name__)

type EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventSubscriber:
    """Consumes events from Redis Streams using consumer groups.

    Usage::

        sub = EventSubscriber(redis_url, group="eval-engine", consumer="eval-1")
        sub.on(EventType.TASK_COMPLETED, handle_task_completed)
        await sub.start([EventType.TASK_COMPLETED])
    """

    def __init__(
        self,
        redis_url: str,
        group: str,
        consumer: str,
        stream_prefix: str = "architect",
    ) -> None:
        self._redis_url = redis_url
        self._group = group
        self._consumer = consumer
        self._stream_prefix = stream_prefix
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._redis: aioredis.Redis | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ── Handler registration ────────────────────────────────────────
    def on(self, event_type: EventType, handler: EventHandler) -> None:
        """Register *handler* to be called for events of *event_type*."""
        self._handlers.setdefault(event_type, []).append(handler)

    # ── Lifecycle ───────────────────────────────────────────────────
    async def start(self, event_types: list[EventType]) -> None:
        """Create consumer groups (if needed) and begin the read loop.

        This method spawns a background ``asyncio.Task`` that reads
        from Redis using ``XREADGROUP`` and dispatches to registered
        handlers.  Messages are acknowledged (``XACK``) only after all
        handlers complete successfully.
        """
        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )

        # Ensure consumer groups exist for each stream.
        for et in event_types:
            stream = self._stream_name(et)
            try:
                await self._redis.xgroup_create(
                    stream,
                    self._group,
                    id="0",
                    mkstream=True,
                )
                logger.info("Created consumer group %s on %s", self._group, stream)
            except aioredis.ResponseError as exc:
                # Group already exists -- that's fine.
                if "BUSYGROUP" not in str(exc):
                    raise

        self._running = True
        self._task = asyncio.create_task(self._read_loop(event_types))
        logger.info(
            "EventSubscriber started (group=%s, consumer=%s, streams=%s)",
            self._group,
            self._consumer,
            [et.value for et in event_types],
        )

    async def stop(self) -> None:
        """Signal the read loop to stop and wait for it to finish."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("EventSubscriber stopped")

    # ── Internals ───────────────────────────────────────────────────
    def _stream_name(self, event_type: EventType) -> str:
        return f"{self._stream_prefix}:{event_type}"

    async def _read_loop(self, event_types: list[EventType]) -> None:
        """Continuously read from Redis Streams via XREADGROUP."""
        assert self._redis is not None

        streams: dict[str, str] = {self._stream_name(et): ">" for et in event_types}

        while self._running:
            try:
                results = await self._redis.xreadgroup(
                    groupname=self._group,
                    consumername=self._consumer,
                    streams=streams,  # type: ignore[arg-type]
                    count=10,
                    block=2000,
                )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in XREADGROUP, retrying in 1 s")
                await asyncio.sleep(1)
                continue

            if not results:
                continue

            for stream_name_bytes, messages in results:
                stream_name = (
                    stream_name_bytes.decode()
                    if isinstance(stream_name_bytes, bytes)
                    else stream_name_bytes
                )
                # Derive event type from stream name.
                event_type_str = stream_name.removeprefix(f"{self._stream_prefix}:")
                try:
                    event_type = EventType(event_type_str)
                except ValueError:
                    logger.warning("Unknown event type in stream %s", stream_name)
                    continue

                handlers = self._handlers.get(event_type, [])

                for message_id, data in messages:
                    try:
                        envelope = deserialize_event(data)
                    except Exception:
                        logger.exception(
                            "Failed to deserialize message %s from %s",
                            message_id,
                            stream_name,
                        )
                        continue

                    for handler in handlers:
                        try:
                            await handler(envelope)
                        except Exception:
                            logger.exception(
                                "Handler %s failed for message %s",
                                handler.__name__,
                                message_id,
                            )
                            # Continue to next handler; do NOT ack.
                            continue

                    # Acknowledge only after all handlers succeed.
                    await self._redis.xack(stream_name, self._group, message_id)  # type: ignore[arg-type]
