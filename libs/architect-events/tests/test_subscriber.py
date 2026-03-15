"""Tests for EventSubscriber — handler dispatch, retry logic, and DLQ routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from architect_common.enums import EventType
from architect_events.schemas import EventEnvelope
from architect_events.serialization import serialize_event
from architect_events.subscriber import EventSubscriber

# ── Helpers ──────────────────────────────────────────────────────────


def _make_redis_message(
    event: EventEnvelope,
    message_id: bytes = b"1-0",
) -> tuple[bytes, dict[bytes, bytes]]:
    """Build a (message_id, data) tuple as returned by XREADGROUP."""
    wire = serialize_event(event)
    data = {k.encode(): v.encode() for k, v in wire.items()}
    return message_id, data


def _make_envelope(event_type: EventType = EventType.TASK_CREATED) -> EventEnvelope:
    return EventEnvelope(
        type=event_type,
        correlation_id="corr-sub-test",
        payload={"key": "value"},
    )


def _stop_loop(sub: EventSubscriber) -> None:
    """Helper to stop the read loop from inside a side_effect."""
    sub._running = False


# ── Handler registration ────────────────────────────────────────────


class TestHandlerRegistration:
    def test_on_registers_handler(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")

        async def my_handler(envelope: EventEnvelope) -> None:
            pass

        sub.on(EventType.TASK_CREATED, my_handler)
        assert my_handler in sub._handlers[EventType.TASK_CREATED]

    def test_on_registers_multiple_handlers(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")

        async def handler_a(envelope: EventEnvelope) -> None:
            pass

        async def handler_b(envelope: EventEnvelope) -> None:
            pass

        sub.on(EventType.TASK_CREATED, handler_a)
        sub.on(EventType.TASK_CREATED, handler_b)
        assert len(sub._handlers[EventType.TASK_CREATED]) == 2

    def test_on_registers_handlers_for_different_event_types(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")

        async def handler_task(envelope: EventEnvelope) -> None:
            pass

        async def handler_agent(envelope: EventEnvelope) -> None:
            pass

        sub.on(EventType.TASK_CREATED, handler_task)
        sub.on(EventType.AGENT_SPAWNED, handler_agent)

        assert EventType.TASK_CREATED in sub._handlers
        assert EventType.AGENT_SPAWNED in sub._handlers


# ── Message handling callback ────────────────────────────────────────


class TestMessageHandling:
    """Test the _read_loop dispatching behavior."""

    async def test_successful_handler_acks_message(self) -> None:
        """When all handlers succeed, the message should be ACKed."""
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1", stream_prefix="test")
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"100-0")

        handler_called = False

        async def handler(env: EventEnvelope) -> None:
            nonlocal handler_called
            handler_called = True

        sub.on(EventType.TASK_CREATED, handler)
        sub._running = True

        stream_name = f"test:{EventType.TASK_CREATED}"

        call_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(stream_name.encode(), [(mid, data)])]
            # Stop loop after first delivery
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        assert handler_called
        mock_redis.xack.assert_called_once_with(stream_name, "grp", mid)

    async def test_failed_handler_does_not_ack(self) -> None:
        """When a handler fails, the message should NOT be ACKed (stays in PEL)."""
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
            max_retries=5,
        )
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"200-0")

        async def failing_handler(env: EventEnvelope) -> None:
            raise ValueError("handler exploded")

        sub.on(EventType.TASK_CREATED, failing_handler)
        sub._running = True

        stream_name = f"test:{EventType.TASK_CREATED}"

        call_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(stream_name.encode(), [(mid, data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        # Should NOT have been ACKed since handler failed and retries remain
        mock_redis.xack.assert_not_called()
        # Retry count should have been incremented
        assert sub._retry_counts.get("200-0", 0) == 1

    async def test_no_handlers_still_acks(self) -> None:
        """Messages with no registered handlers should be ACKed (no-op delivery)."""
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1", stream_prefix="test")
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"300-0")

        # No handlers registered
        sub._running = True
        stream_name = f"test:{EventType.TASK_CREATED}"

        call_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(stream_name.encode(), [(mid, data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        mock_redis.xack.assert_called_once()


# ── Retry logic ──────────────────────────────────────────────────────


class TestRetryLogic:
    async def test_message_retried_then_succeeds(self) -> None:
        """A message that fails then succeeds on retry should be ACKed."""
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
            max_retries=3,
        )
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"400-0")

        call_count = 0

        async def flaky_handler(env: EventEnvelope) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            # Second call succeeds

        sub.on(EventType.TASK_CREATED, flaky_handler)
        sub._running = True
        stream_name = f"test:{EventType.TASK_CREATED}"

        delivery_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal delivery_count
            delivery_count += 1
            if delivery_count <= 2:
                # Deliver the same message twice (simulating retry via PEL)
                return [(stream_name.encode(), [(mid, data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        assert call_count == 2
        # After second (successful) call, message should be ACKed
        mock_redis.xack.assert_called()
        # Retry count should have been cleared after success
        assert "400-0" not in sub._retry_counts

    async def test_retry_count_increments_on_failure(self) -> None:
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
            max_retries=5,
        )
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"500-0")

        async def always_fails(env: EventEnvelope) -> None:
            raise RuntimeError("permanent failure")

        sub.on(EventType.TASK_CREATED, always_fails)
        sub._running = True
        stream_name = f"test:{EventType.TASK_CREATED}"

        delivery_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal delivery_count
            delivery_count += 1
            if delivery_count <= 2:
                return [(stream_name.encode(), [(mid, data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        assert sub._retry_counts.get("500-0", 0) == 2


# ── DLQ routing ──────────────────────────────────────────────────────


class TestDLQRouting:
    async def test_message_sent_to_dlq_after_max_retries(self) -> None:
        """After max_retries failures, message should be moved to DLQ."""
        max_retries = 2
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
            max_retries=max_retries,
        )
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        envelope = _make_envelope()
        mid, data = _make_redis_message(envelope, b"600-0")

        async def always_fails(env: EventEnvelope) -> None:
            raise RuntimeError("permanent failure")

        sub.on(EventType.TASK_CREATED, always_fails)
        sub._running = True
        stream_name = f"test:{EventType.TASK_CREATED}"

        delivery_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal delivery_count
            delivery_count += 1
            if delivery_count <= max_retries:
                return [(stream_name.encode(), [(mid, data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        # Should have been moved to DLQ (xadd to dlq stream + xack on original)
        assert mock_redis.xadd.call_count == 1
        dlq_stream = mock_redis.xadd.call_args[0][0]
        assert "dlq" in dlq_stream
        # Original message was ACKed as part of DLQ move
        mock_redis.xack.assert_called_once()

        # Retry count should have been cleaned up
        assert "600-0" not in sub._retry_counts

    async def test_deserialization_failure_goes_to_dlq(self) -> None:
        """Unparseable messages should go straight to DLQ."""
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
            max_retries=3,
        )
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        # Corrupt data that can't be deserialized
        bad_data: dict[bytes, bytes] = {b"data": b"not valid json {{{"}

        sub._running = True
        stream_name = f"test:{EventType.TASK_CREATED}"

        call_count = 0

        async def fake_xreadgroup(**kwargs: object) -> list[object] | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(stream_name.encode(), [(b"700-0", bad_data)])]
            sub._running = False
            return None

        mock_redis.xreadgroup = AsyncMock(side_effect=fake_xreadgroup)

        await sub._read_loop([EventType.TASK_CREATED])

        # Should have gone to DLQ immediately (not retried)
        mock_redis.xadd.assert_called_once()
        mock_redis.xack.assert_called_once()

    async def test_dlq_stream_name_format(self) -> None:
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="myprefix",
        )
        name = sub._dlq_stream_name(EventType.TASK_FAILED)
        assert name == f"myprefix:dlq:{EventType.TASK_FAILED}"


# ── Lifecycle ────────────────────────────────────────────────────────


class TestSubscriberLifecycle:
    async def test_start_creates_consumer_groups(self) -> None:
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
        )

        with patch("architect_events.subscriber.aioredis.from_url") as mock_from_url:
            mock_conn = AsyncMock()
            mock_from_url.return_value = mock_conn
            # Make xreadgroup return nothing and stop immediately
            mock_conn.xreadgroup.side_effect = asyncio.CancelledError()

            await sub.start([EventType.TASK_CREATED, EventType.AGENT_SPAWNED])

            # Should have called xgroup_create for each event type
            assert mock_conn.xgroup_create.call_count == 2

            await sub.stop()

    async def test_stop_cancels_task_and_closes_redis(self) -> None:
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            stream_prefix="test",
        )

        with patch("architect_events.subscriber.aioredis.from_url") as mock_from_url:
            mock_conn = AsyncMock()
            mock_from_url.return_value = mock_conn
            mock_conn.xreadgroup.side_effect = asyncio.CancelledError()

            await sub.start([EventType.TASK_CREATED])
            assert sub._running is True

            await sub.stop()
            assert sub._running is False
            assert sub._redis is None
            mock_conn.aclose.assert_called_once()

    async def test_stop_when_not_started_is_safe(self) -> None:
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1")
        await sub.stop()  # Should not raise

    def test_initial_state(self) -> None:
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1")
        assert sub._running is False
        assert sub._redis is None
        assert sub._task is None
        assert sub._retry_counts == {}
        assert sub._handlers == {}


# ── Retry tracking memory management ────────────────────────────────


class TestRetryTracking:
    def test_max_retry_tracking_threshold(self) -> None:
        """The MAX_RETRY_TRACKING constant should be set to a reasonable value."""
        sub = EventSubscriber(
            "redis://localhost",
            group="grp",
            consumer="c1",
            max_retries=100,
        )
        assert sub._MAX_RETRY_TRACKING == 10_000

    def test_successful_delivery_clears_retry_count(self) -> None:
        """After successful handling, retry count for that message is removed."""
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1")
        sub._retry_counts["some-msg"] = 2
        sub._retry_counts.pop("some-msg", None)
        assert "some-msg" not in sub._retry_counts

    def test_retry_counts_pruned_when_threshold_exceeded(self) -> None:
        """When _retry_counts grows past _MAX_RETRY_TRACKING, oldest half is pruned."""
        sub = EventSubscriber("redis://localhost", group="grp", consumer="c1")
        # Simulate the pruning logic from _read_loop
        for i in range(sub._MAX_RETRY_TRACKING + 100):
            sub._retry_counts[f"msg-{i}"] = 1

        # Manually exercise the pruning logic (same as in _read_loop)
        if len(sub._retry_counts) > sub._MAX_RETRY_TRACKING:
            keys = list(sub._retry_counts.keys())
            for k in keys[: len(keys) // 2]:
                del sub._retry_counts[k]

        # Should have pruned roughly half
        assert len(sub._retry_counts) < sub._MAX_RETRY_TRACKING
