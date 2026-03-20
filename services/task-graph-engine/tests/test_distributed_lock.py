"""Tests for distributed scheduler lock (in-memory fallback mode)."""

from __future__ import annotations

import pytest

from task_graph_engine.distributed_lock import DistributedSchedulerLock


@pytest.fixture
def lock() -> DistributedSchedulerLock:
    return DistributedSchedulerLock()  # No redis_url = in-memory mode


class TestDistributedLockInMemory:
    async def test_schedule_lock_context(self, lock: DistributedSchedulerLock) -> None:
        async with lock.schedule_lock():
            pass  # Should not raise

    async def test_try_claim_always_succeeds_in_memory(
        self, lock: DistributedSchedulerLock
    ) -> None:
        assert await lock.try_claim_task("task-1") is True
        # In-memory mode always succeeds
        assert await lock.try_claim_task("task-1") is True

    async def test_mark_and_get_completed(self, lock: DistributedSchedulerLock) -> None:
        await lock.mark_completed("task-1")
        await lock.mark_completed("task-2")
        completed = await lock.get_completed()
        assert completed == {"task-1", "task-2"}

    async def test_reset_clears_state(self, lock: DistributedSchedulerLock) -> None:
        await lock.mark_completed("task-1")
        await lock.reset()
        completed = await lock.get_completed()
        assert len(completed) == 0

    async def test_get_completed_returns_copy(self, lock: DistributedSchedulerLock) -> None:
        """Ensure get_completed returns a copy, not a reference."""
        await lock.mark_completed("task-1")
        completed = await lock.get_completed()
        completed.add("task-fake")
        assert "task-fake" not in await lock.get_completed()

    async def test_connect_noop_without_url(self, lock: DistributedSchedulerLock) -> None:
        """connect() with no redis_url should be a safe no-op."""
        await lock.connect()
        assert lock._redis is None

    async def test_close_noop_without_connection(self, lock: DistributedSchedulerLock) -> None:
        """close() without a prior connect should be a safe no-op."""
        await lock.close()
        assert lock._redis is None
