"""Tests for the event DLQ and subscriber retry/DLQ behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from architect_common.enums import EventType
from architect_events.dlq import DeadLetterProcessor
from architect_events.subscriber import EventSubscriber

# ── DeadLetterProcessor tests ────────────────────────────────────────


class TestDeadLetterProcessor:
    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        r = AsyncMock()
        r.xlen = AsyncMock(return_value=5)
        r.xrange = AsyncMock(return_value=[])
        r.delete = AsyncMock()
        r.aclose = AsyncMock()
        return r

    @pytest.fixture
    def processor(self, mock_redis: AsyncMock) -> DeadLetterProcessor:
        dlp = DeadLetterProcessor("redis://localhost", stream_prefix="test")
        dlp._redis = mock_redis
        return dlp

    async def test_count(self, processor: DeadLetterProcessor, mock_redis: AsyncMock) -> None:
        result = await processor.count(EventType.TASK_CREATED)
        assert result == 5
        mock_redis.xlen.assert_called_once_with(f"test:dlq:{EventType.TASK_CREATED}")

    async def test_purge(self, processor: DeadLetterProcessor, mock_redis: AsyncMock) -> None:
        await processor.purge(EventType.TASK_CREATED)
        mock_redis.delete.assert_called_once_with(f"test:dlq:{EventType.TASK_CREATED}")

    async def test_reprocess_empty(
        self, processor: DeadLetterProcessor, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrange.return_value = []
        result = await processor.reprocess(EventType.TASK_CREATED, count=10)
        assert result == 0

    async def test_reprocess_strips_metadata(
        self, processor: DeadLetterProcessor, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrange.return_value = [
            (
                b"1-0",
                {
                    b"original_stream": b"test:task.created",
                    b"original_id": b"0-1",
                    b"error": b"handler failed",
                    b"payload": b'{"key": "value"}',
                },
            ),
        ]
        result = await processor.reprocess(EventType.TASK_CREATED, count=10)
        assert result == 1
        # Should have re-published only the payload, not the DLQ metadata
        call_args = mock_redis.xadd.call_args
        published_data = call_args[0][1]
        assert b"original_stream" not in published_data
        assert b"error" not in published_data
        assert b"payload" in published_data

    async def test_connect_and_close(self) -> None:
        dlp = DeadLetterProcessor("redis://localhost")
        with patch("architect_events.dlq.aioredis.from_url") as mock_from_url:
            mock_conn = AsyncMock()
            mock_from_url.return_value = mock_conn
            await dlp.connect()
            assert dlp._redis is not None
            await dlp.close()
            mock_conn.aclose.assert_called_once()


# ── Subscriber retry/DLQ tests ──────────────────────────────────────


class TestSubscriberDLQ:
    def test_max_retries_default(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")
        assert sub._max_retries == 3

    def test_max_retries_custom(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c", max_retries=5)
        assert sub._max_retries == 5

    def test_retry_counts_initialized_empty(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")
        assert sub._retry_counts == {}

    async def test_move_to_dlq(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c", stream_prefix="test")
        mock_redis = AsyncMock()
        sub._redis = mock_redis

        await sub._move_to_dlq(
            "test:task.created",
            EventType.TASK_CREATED,
            b"1-0",
            {b"payload": b"data"},
            "handler failed",
        )

        # Should XADD to DLQ
        mock_redis.xadd.assert_called_once()
        dlq_stream = mock_redis.xadd.call_args[0][0]
        assert "dlq" in dlq_stream

        # Should ACK the original
        mock_redis.xack.assert_called_once()

    async def test_get_dlq_messages(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c", stream_prefix="test")
        mock_redis = AsyncMock()
        mock_redis.xrange.return_value = [
            (b"1-0", {b"payload": b"data1"}),
            (b"2-0", {b"payload": b"data2"}),
        ]
        sub._redis = mock_redis

        msgs = await sub.get_dlq_messages(EventType.TASK_CREATED, count=50)
        assert len(msgs) == 2
        assert msgs[0][0] == "1-0"
        assert msgs[0][1]["payload"] == "data1"

    async def test_get_dlq_messages_not_started_raises(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")
        with pytest.raises(RuntimeError, match="not started"):
            await sub.get_dlq_messages(EventType.TASK_CREATED)

    async def test_claim_stale_messages(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c", stream_prefix="test")
        mock_redis = AsyncMock()
        # First call returns some messages, second returns empty
        mock_redis.xautoclaim.side_effect = [
            (b"0-0", [(b"1-0", {b"data": b"val"})], []),
        ]
        sub._redis = mock_redis

        claimed = await sub.claim_stale_messages([EventType.TASK_CREATED], idle_ms=30_000)
        assert claimed == 1

    async def test_claim_stale_not_started_raises(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c")
        with pytest.raises(RuntimeError, match="not started"):
            await sub.claim_stale_messages([EventType.TASK_CREATED])

    def test_dlq_stream_name(self) -> None:
        sub = EventSubscriber("redis://localhost", group="g", consumer="c", stream_prefix="arch")
        name = sub._dlq_stream_name(EventType.TASK_CREATED)
        assert name == f"arch:dlq:{EventType.TASK_CREATED}"
