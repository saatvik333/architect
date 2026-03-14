"""Redis Streams consumer-group event subscriber with DLQ support."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis

from architect_common.enums import EventType
from architect_events.schemas import EventEnvelope
from architect_events.serialization import deserialize_event

logger = logging.getLogger(__name__)

type EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventSubscriber:
    """Consumes events from Redis Streams using consumer groups.

    Failed messages are retried up to ``max_retries`` times before being
    moved to a dead-letter queue stream (``{prefix}:dlq:{event_type}``).

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
        max_retries: int = 3,
    ) -> None:
        self._redis_url = redis_url
        self._group = group
        self._consumer = consumer
        self._stream_prefix = stream_prefix
        self._max_retries = max_retries
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._redis: aioredis.Redis | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._retry_counts: dict[str, int] = {}

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

    # ── DLQ helpers ──────────────────────────────────────────────────

    def _dlq_stream_name(self, event_type: EventType) -> str:
        return f"{self._stream_prefix}:dlq:{event_type}"

    async def _move_to_dlq(
        self,
        stream_name: str,
        event_type: EventType,
        message_id: bytes | str,
        data: dict[Any, Any],
        error: str,
    ) -> None:
        """Move a failed message to the dead-letter queue."""
        assert self._redis is not None
        dlq_stream = self._dlq_stream_name(event_type)
        mid_str = message_id.decode() if isinstance(message_id, bytes) else message_id
        dlq_fields: dict[str | bytes, str | bytes] = {
            b"original_stream": stream_name.encode(),
            b"original_id": mid_str.encode(),
            b"error": error.encode(),
        }
        # Copy original data
        for k, v in data.items():
            key = k if isinstance(k, bytes) else k.encode()
            val = v if isinstance(v, bytes) else str(v).encode()
            dlq_fields[key] = val

        await self._redis.xadd(dlq_stream, dlq_fields)  # type: ignore[arg-type]
        # ACK the original so it doesn't stay in PEL
        await self._redis.xack(stream_name, self._group, message_id)
        logger.warning(
            "Moved message %s to DLQ %s after %d retries",
            mid_str,
            dlq_stream,
            self._max_retries,
        )

    async def claim_stale_messages(
        self,
        event_types: list[EventType],
        idle_ms: int = 60_000,
    ) -> int:
        """Reclaim messages stuck in other consumers using XAUTOCLAIM.

        Returns the number of messages claimed.
        """
        if self._redis is None:
            msg = "Subscriber not started"
            raise RuntimeError(msg)

        total_claimed = 0
        for et in event_types:
            stream = self._stream_name(et)
            start_id = "0-0"
            while True:
                result = await self._redis.xautoclaim(
                    stream,
                    self._group,
                    self._consumer,
                    min_idle_time=idle_ms,
                    start_id=start_id,
                    count=100,
                )
                # result = (next_start_id, claimed_messages, deleted_ids)
                next_start, claimed, _ = result
                total_claimed += len(claimed)
                next_str = next_start.decode() if isinstance(next_start, bytes) else next_start
                if next_str == "0-0" or not claimed:
                    break
                start_id = next_str

        logger.info("Claimed %d stale messages", total_claimed)
        return total_claimed

    async def get_dlq_messages(
        self,
        event_type: EventType,
        count: int = 100,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Read messages from the DLQ for inspection.

        Returns a list of ``(message_id, data)`` tuples.
        """
        if self._redis is None:
            msg = "Subscriber not started"
            raise RuntimeError(msg)

        dlq_stream = self._dlq_stream_name(event_type)
        results = await self._redis.xrange(dlq_stream, count=count)
        out: list[tuple[str, dict[str, Any]]] = []
        for mid, data in results:
            mid_str = mid.decode() if isinstance(mid, bytes) else mid
            decoded = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in data.items()
            }
            out.append((mid_str, decoded))
        return out

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
                    mid_str = (
                        message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                    )
                    try:
                        envelope = deserialize_event(data)
                    except Exception:
                        logger.exception(
                            "Failed to deserialize message %s from %s",
                            message_id,
                            stream_name,
                        )
                        # Deserialization failures go straight to DLQ
                        await self._move_to_dlq(
                            stream_name, event_type, message_id, data, "deserialization_error"
                        )
                        continue

                    handler_failed = False
                    last_error = ""
                    for handler in handlers:
                        try:
                            await handler(envelope)
                        except Exception as exc:
                            logger.exception(
                                "Handler %s failed for message %s",
                                handler.__name__,
                                message_id,
                            )
                            handler_failed = True
                            last_error = f"{handler.__name__}: {exc}"
                            break

                    if handler_failed:
                        retry_count = self._retry_counts.get(mid_str, 0) + 1
                        self._retry_counts[mid_str] = retry_count

                        if retry_count >= self._max_retries:
                            await self._move_to_dlq(
                                stream_name, event_type, message_id, data, last_error
                            )
                            self._retry_counts.pop(mid_str, None)
                        # else: don't ACK — message stays in PEL for retry
                    else:
                        # All handlers succeeded — acknowledge.
                        await self._redis.xack(stream_name, self._group, message_id)
                        self._retry_counts.pop(mid_str, None)
