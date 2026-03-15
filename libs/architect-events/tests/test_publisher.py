"""Tests for EventPublisher — publish, error handling, and serialization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from architect_common.enums import EventType
from architect_events.publisher import EventPublisher
from architect_events.schemas import EventEnvelope

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Return a mock async Redis client."""
    r = AsyncMock()
    # xadd returns a bytes message ID
    r.xadd = AsyncMock(return_value=b"1234567890-0")
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def publisher(mock_redis: AsyncMock) -> EventPublisher:
    """Return an EventPublisher with a pre-injected mock Redis."""
    pub = EventPublisher("redis://localhost:6379", stream_prefix="test")
    pub._redis = mock_redis
    return pub


@pytest.fixture
def sample_event() -> EventEnvelope:
    return EventEnvelope(
        type=EventType.TASK_CREATED,
        correlation_id="corr-pub-test",
        payload={"task_id": "task-abc123"},
    )


# ── Publish happy-path ──────────────────────────────────────────────


class TestPublish:
    async def test_publish_returns_message_id(
        self, publisher: EventPublisher, sample_event: EventEnvelope
    ) -> None:
        mid = await publisher.publish(sample_event)
        assert mid == "1234567890-0"

    async def test_publish_calls_xadd_with_correct_stream(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        await publisher.publish(sample_event)

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        stream_name = call_args[0][0]
        assert stream_name == f"test:{EventType.TASK_CREATED}"

    async def test_publish_sends_serialized_data(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        await publisher.publish(sample_event)

        call_args = mock_redis.xadd.call_args
        fields = call_args[0][1]
        assert "data" in fields
        # The data field should be valid JSON containing the event type
        assert EventType.TASK_CREATED.value in fields["data"]

    async def test_publish_uses_maxlen(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        await publisher.publish(sample_event)

        call_kwargs = mock_redis.xadd.call_args
        assert call_kwargs.kwargs.get("maxlen") == 10_000
        assert call_kwargs.kwargs.get("approximate") is True

    async def test_publish_multiple_events_different_streams(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
    ) -> None:
        """Different event types should go to different streams."""
        evt1 = EventEnvelope(type=EventType.TASK_CREATED)
        evt2 = EventEnvelope(type=EventType.AGENT_SPAWNED)

        await publisher.publish(evt1)
        await publisher.publish(evt2)

        assert mock_redis.xadd.call_count == 2
        streams = [call[0][0] for call in mock_redis.xadd.call_args_list]
        assert f"test:{EventType.TASK_CREATED}" in streams
        assert f"test:{EventType.AGENT_SPAWNED}" in streams

    async def test_publish_preserves_correlation_id(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
    ) -> None:
        evt = EventEnvelope(
            type=EventType.TASK_COMPLETED,
            correlation_id="corr-999",
            payload={"verdict": "pass"},
        )
        await publisher.publish(evt)

        fields = mock_redis.xadd.call_args[0][1]
        assert "corr-999" in fields["data"]

    async def test_publish_handles_bytes_message_id(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        """xadd may return bytes; publish should decode to str."""
        mock_redis.xadd.return_value = b"9999999-42"
        mid = await publisher.publish(sample_event)
        assert mid == "9999999-42"
        assert isinstance(mid, str)

    async def test_publish_handles_str_message_id(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        """Some Redis drivers may return str directly."""
        mock_redis.xadd.return_value = "1111111-0"
        mid = await publisher.publish(sample_event)
        assert mid == "1111111-0"


# ── Error handling ──────────────────────────────────────────────────


class TestPublishErrors:
    async def test_publish_raises_when_not_connected(self) -> None:
        """Calling publish() before connect() should raise RuntimeError."""
        pub = EventPublisher("redis://localhost:6379")
        evt = EventEnvelope(type=EventType.TASK_CREATED)

        with pytest.raises(RuntimeError, match="not connected"):
            await pub.publish(evt)

    async def test_publish_propagates_redis_error(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        """Redis errors should propagate to the caller."""
        mock_redis.xadd.side_effect = ConnectionError("Connection lost")

        with pytest.raises(ConnectionError, match="Connection lost"):
            await publisher.publish(sample_event)

    async def test_publish_propagates_timeout_error(
        self,
        publisher: EventPublisher,
        mock_redis: AsyncMock,
        sample_event: EventEnvelope,
    ) -> None:
        mock_redis.xadd.side_effect = TimeoutError("Redis timeout")

        with pytest.raises(TimeoutError, match="Redis timeout"):
            await publisher.publish(sample_event)


# ── Connection lifecycle ────────────────────────────────────────────


class TestPublisherLifecycle:
    async def test_connect_creates_redis_client(self) -> None:
        pub = EventPublisher("redis://localhost:6379")
        assert pub._redis is None

        with patch("architect_events.publisher.aioredis.from_url") as mock_from_url:
            mock_conn = AsyncMock()
            mock_from_url.return_value = mock_conn
            await pub.connect()

            assert pub._redis is mock_conn
            mock_from_url.assert_called_once_with("redis://localhost:6379", decode_responses=False)

    async def test_close_cleans_up_connection(self, mock_redis: AsyncMock) -> None:
        pub = EventPublisher("redis://localhost:6379")
        pub._redis = mock_redis

        await pub.close()

        mock_redis.aclose.assert_called_once()
        assert pub._redis is None

    async def test_close_when_not_connected_is_noop(self) -> None:
        """Closing before connecting should not raise."""
        pub = EventPublisher("redis://localhost:6379")
        await pub.close()  # Should not raise

    async def test_double_close_is_safe(self, mock_redis: AsyncMock) -> None:
        pub = EventPublisher("redis://localhost:6379")
        pub._redis = mock_redis

        await pub.close()
        await pub.close()  # Second close should be a no-op

        mock_redis.aclose.assert_called_once()


# ── Stream naming ───────────────────────────────────────────────────


class TestStreamNaming:
    def test_stream_name_uses_prefix_and_event_type(self) -> None:
        pub = EventPublisher("redis://localhost:6379", stream_prefix="myapp")
        evt = EventEnvelope(type=EventType.TASK_FAILED)
        assert pub._stream_name(evt) == f"myapp:{EventType.TASK_FAILED}"

    def test_default_prefix_is_architect(self) -> None:
        pub = EventPublisher("redis://localhost:6379")
        evt = EventEnvelope(type=EventType.AGENT_COMPLETED)
        assert pub._stream_name(evt) == f"architect:{EventType.AGENT_COMPLETED}"
