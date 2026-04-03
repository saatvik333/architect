"""FastAPI dependency injection for the Knowledge & Memory service."""

from __future__ import annotations

from functools import lru_cache

from architect_common.dependencies import ServiceDependency
from knowledge_memory.config import KnowledgeMemoryConfig
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.working_memory import WorkingMemoryStore


@lru_cache(maxsize=1)
def get_config() -> KnowledgeMemoryConfig:
    """Return the cached service configuration."""
    return KnowledgeMemoryConfig()


_knowledge_store = ServiceDependency[KnowledgeStore]("KnowledgeStore")
_working_memory = ServiceDependency[WorkingMemoryStore]("WorkingMemoryStore")
_heuristic_engine = ServiceDependency[HeuristicEngine]("HeuristicEngine")

get_knowledge_store = _knowledge_store.get
set_knowledge_store = _knowledge_store.set
get_working_memory = _working_memory.get
set_working_memory = _working_memory.set
get_heuristic_engine = _heuristic_engine.get
set_heuristic_engine = _heuristic_engine.set


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _knowledge_store.cleanup()
    await _working_memory.cleanup()
    await _heuristic_engine.cleanup()
