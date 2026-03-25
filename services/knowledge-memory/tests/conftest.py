"""Shared pytest fixtures for knowledge-memory tests."""

from __future__ import annotations

import pytest

from knowledge_memory.config import KnowledgeMemoryConfig
from knowledge_memory.working_memory import WorkingMemoryStore


@pytest.fixture
def config() -> KnowledgeMemoryConfig:
    """Return the default service configuration."""
    return KnowledgeMemoryConfig()


@pytest.fixture
def working_memory_store() -> WorkingMemoryStore:
    """Return a fresh WorkingMemoryStore with short TTL for testing."""
    return WorkingMemoryStore(ttl_seconds=5, max_entries=10)
