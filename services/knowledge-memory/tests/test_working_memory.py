"""Tests for the L0 working memory store."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from architect_common.types import AgentId, KnowledgeId, TaskId, utcnow
from knowledge_memory.working_memory import WorkingMemoryStore


class TestWorkingMemoryStore:
    """Tests for WorkingMemoryStore operations."""

    async def test_create_and_get(self, working_memory_store: WorkingMemoryStore) -> None:
        """create() should make an entry retrievable by get()."""
        task_id = TaskId("task-wm001")
        agent_id = AgentId("agent-wm001")

        wm = await working_memory_store.create(task_id, agent_id)
        assert wm.task_id == task_id
        assert wm.agent_id == agent_id
        assert wm.scratchpad == {}

        retrieved = await working_memory_store.get(task_id, agent_id)
        assert retrieved is not None
        assert retrieved.task_id == task_id

    async def test_get_nonexistent(self, working_memory_store: WorkingMemoryStore) -> None:
        """get() should return None for non-existent entries."""
        result = await working_memory_store.get(
            TaskId("task-nonexistent"), AgentId("agent-nonexistent")
        )
        assert result is None

    async def test_update_scratchpad(self, working_memory_store: WorkingMemoryStore) -> None:
        """update() should merge scratchpad updates."""
        task_id = TaskId("task-update001")
        agent_id = AgentId("agent-update001")

        await working_memory_store.create(task_id, agent_id)
        updated = await working_memory_store.update(
            task_id, agent_id, scratchpad_updates={"key1": "value1"}
        )

        assert updated is not None
        assert updated.scratchpad["key1"] == "value1"

        # Subsequent update should merge
        updated2 = await working_memory_store.update(
            task_id, agent_id, scratchpad_updates={"key2": "value2"}
        )
        assert updated2 is not None
        assert updated2.scratchpad["key1"] == "value1"
        assert updated2.scratchpad["key2"] == "value2"

    async def test_update_context_entries(self, working_memory_store: WorkingMemoryStore) -> None:
        """update() should append context entries."""
        task_id = TaskId("task-ctx001")
        agent_id = AgentId("agent-ctx001")

        await working_memory_store.create(task_id, agent_id)
        updated = await working_memory_store.update(
            task_id,
            agent_id,
            add_context_entries=[KnowledgeId("know-ctx1")],
        )

        assert updated is not None
        assert len(updated.context_entries) == 1

    async def test_update_nonexistent(self, working_memory_store: WorkingMemoryStore) -> None:
        """update() should return None for non-existent entries."""
        result = await working_memory_store.update(
            TaskId("task-nope"), AgentId("agent-nope"), scratchpad_updates={"k": "v"}
        )
        assert result is None

    async def test_delete(self, working_memory_store: WorkingMemoryStore) -> None:
        """delete() should remove the entry."""
        task_id = TaskId("task-del001")
        agent_id = AgentId("agent-del001")

        await working_memory_store.create(task_id, agent_id)
        assert await working_memory_store.delete(task_id, agent_id) is True
        assert await working_memory_store.get(task_id, agent_id) is None

    async def test_delete_nonexistent(self, working_memory_store: WorkingMemoryStore) -> None:
        """delete() should return False for non-existent entries."""
        assert (
            await working_memory_store.delete(TaskId("task-nope"), AgentId("agent-nope")) is False
        )

    async def test_evict_expired(self) -> None:
        """evict_expired() should remove entries past the TTL."""
        store = WorkingMemoryStore(ttl_seconds=60, max_entries=100)
        task_id = TaskId("task-evict001")
        agent_id = AgentId("agent-evict001")

        await store.create(task_id, agent_id)
        assert store.size == 1

        # Advance time past TTL without actually sleeping
        future_time = utcnow() + timedelta(seconds=61)
        with patch("knowledge_memory.working_memory.utcnow", return_value=future_time):
            evicted = await store.evict_expired()
        assert evicted == 1
        assert store.size == 0

    async def test_max_entries_eviction(self) -> None:
        """Creating entries beyond max_entries should evict the oldest."""
        store = WorkingMemoryStore(ttl_seconds=3600, max_entries=3)

        for i in range(4):
            await store.create(TaskId(f"task-max{i:03d}"), AgentId("agent-max001"))

        # Should have evicted the oldest to make room
        assert store.size <= 3

    async def test_size_property(self, working_memory_store: WorkingMemoryStore) -> None:
        """size property should reflect current entry count."""
        assert working_memory_store.size == 0
        await working_memory_store.create(TaskId("task-sz001"), AgentId("agent-sz001"))
        assert working_memory_store.size == 1
        await working_memory_store.create(TaskId("task-sz002"), AgentId("agent-sz002"))
        assert working_memory_store.size == 2
