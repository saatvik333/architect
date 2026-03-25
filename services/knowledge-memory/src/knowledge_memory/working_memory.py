"""L0 in-process working memory with TTL eviction.

Working memory is keyed by ``(task_id, agent_id)`` and provides a mutable
scratchpad for agents during task execution.  Entries are evicted after
a configurable TTL to prevent unbounded memory growth.
"""

from __future__ import annotations

import asyncio

from architect_common.logging import get_logger
from architect_common.types import AgentId, KnowledgeId, TaskId, utcnow
from knowledge_memory.models import WorkingMemory

logger = get_logger(component="knowledge_memory.working_memory")


class WorkingMemoryStore:
    """In-process L0 working memory store with TTL-based eviction."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 3600,
        max_entries: int = 1000,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[tuple[str, str], WorkingMemory] = {}
        self._lock = asyncio.Lock()

    async def create(self, task_id: TaskId, agent_id: AgentId) -> WorkingMemory:
        """Create a new working memory entry for the task-agent pair."""
        key = (str(task_id), str(agent_id))
        now = utcnow()
        wm = WorkingMemory(
            task_id=task_id,
            agent_id=agent_id,
            created_at=now,
            last_accessed=now,
        )
        async with self._lock:
            # Enforce max entries
            if len(self._store) >= self._max_entries and key not in self._store:
                await self._evict_oldest_unlocked()
            self._store[key] = wm
        logger.debug("created working memory", task_id=str(task_id), agent_id=str(agent_id))
        return wm

    async def get(self, task_id: TaskId, agent_id: AgentId) -> WorkingMemory | None:
        """Retrieve working memory for the task-agent pair, or None if absent."""
        key = (str(task_id), str(agent_id))
        async with self._lock:
            wm = self._store.get(key)
            if wm is not None:
                wm.last_accessed = utcnow()
            return wm

    async def update(
        self,
        task_id: TaskId,
        agent_id: AgentId,
        *,
        scratchpad_updates: dict[str, object] | None = None,
        add_context_entries: list[KnowledgeId] | None = None,
    ) -> WorkingMemory | None:
        """Update the working memory for the task-agent pair.

        Returns the updated working memory, or None if it does not exist.
        """
        key = (str(task_id), str(agent_id))
        async with self._lock:
            wm = self._store.get(key)
            if wm is None:
                return None
            if scratchpad_updates:
                wm.scratchpad.update(scratchpad_updates)
            if add_context_entries:
                wm.context_entries.extend(add_context_entries)
            wm.last_accessed = utcnow()
            return wm

    async def delete(self, task_id: TaskId, agent_id: AgentId) -> bool:
        """Delete working memory for the task-agent pair.

        Returns True if the entry existed and was removed.
        """
        key = (str(task_id), str(agent_id))
        async with self._lock:
            if key in self._store:
                del self._store[key]
                logger.debug("deleted working memory", task_id=str(task_id), agent_id=str(agent_id))
                return True
            return False

    async def evict_expired(self) -> int:
        """Remove entries that have exceeded the TTL.

        Returns the number of entries evicted.
        """
        now = utcnow()
        evicted = 0
        async with self._lock:
            expired_keys = [
                key
                for key, wm in self._store.items()
                if (now - wm.last_accessed).total_seconds() > self._ttl_seconds
            ]
            for key in expired_keys:
                del self._store[key]
                evicted += 1
        if evicted > 0:
            logger.info("evicted expired working memory entries", count=evicted)
        return evicted

    async def _evict_oldest_unlocked(self) -> None:
        """Evict the oldest entry when at capacity.  Caller must hold _lock."""
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k].last_accessed)
        del self._store[oldest_key]
        logger.debug("evicted oldest working memory entry", key=oldest_key)

    @property
    def size(self) -> int:
        """Current number of entries in working memory."""
        return len(self._store)
