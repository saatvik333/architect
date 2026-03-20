"""Distributed locking for horizontal scheduler scaling."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import redis.asyncio as aioredis

from architect_common.logging import get_logger

logger = get_logger(component="distributed_lock")

_LOCK_KEY = "architect:scheduler:lock"
_CLAIMED_PREFIX = "architect:scheduler:claimed:"
_COMPLETED_KEY = "architect:scheduler:completed"


class DistributedSchedulerLock:
    """Redis-backed distributed lock and task claim coordination.

    Falls back to in-memory locking when no Redis URL is configured.
    """

    def __init__(self, redis_url: str = "") -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._local_lock = asyncio.Lock()
        self._local_completed: set[str] = set()

    async def connect(self) -> None:
        if self._redis_url:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            logger.info("distributed_lock_connected")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @asynccontextmanager
    async def schedule_lock(self) -> AsyncIterator[None]:
        """Acquire a distributed scheduling lock."""
        if self._redis is not None:
            # Simple Redis SETNX-based lock with TTL
            lock_acquired = False
            try:
                lock_acquired = await self._redis.set(_LOCK_KEY, "1", nx=True, ex=30)
                if not lock_acquired:
                    # Wait briefly and retry once
                    await asyncio.sleep(0.1)
                    lock_acquired = await self._redis.set(_LOCK_KEY, "1", nx=True, ex=30)
                if not lock_acquired:
                    raise RuntimeError("Could not acquire scheduler lock")
                yield
            finally:
                if lock_acquired:
                    await self._redis.delete(_LOCK_KEY)
        else:
            async with self._local_lock:
                yield

    async def try_claim_task(self, task_id: str) -> bool:
        """Atomically claim a task. Returns True if this caller won the claim."""
        if self._redis is not None:
            key = f"{_CLAIMED_PREFIX}{task_id}"
            return bool(await self._redis.set(key, "1", nx=True, ex=3600))
        # In-memory: always succeed (single process)
        return True

    async def mark_completed(self, task_id: str) -> None:
        """Mark a task as completed in distributed state."""
        if self._redis is not None:
            result: Any = self._redis.sadd(_COMPLETED_KEY, task_id)
            await result
            del_result: Any = self._redis.delete(f"{_CLAIMED_PREFIX}{task_id}")
            await del_result
        self._local_completed.add(task_id)

    async def get_completed(self) -> set[str]:
        """Return the set of completed task IDs."""
        if self._redis is not None:
            members_result: Any = self._redis.smembers(_COMPLETED_KEY)
            members = await members_result
            return cast(set[str], set(members))
        return self._local_completed.copy()

    async def reset(self) -> None:
        """Clear all distributed state (for testing)."""
        if self._redis is not None:
            keys: list[str] = []
            async for key in self._redis.scan_iter(f"{_CLAIMED_PREFIX}*"):
                keys.append(key)
            keys.extend([_LOCK_KEY, _COMPLETED_KEY])
            if keys:
                await self._redis.delete(*keys)
        self._local_completed.clear()
