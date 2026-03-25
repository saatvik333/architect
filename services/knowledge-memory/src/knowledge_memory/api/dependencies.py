"""FastAPI dependency injection for the Knowledge & Memory service."""

from __future__ import annotations

from functools import lru_cache

from knowledge_memory.config import KnowledgeMemoryConfig
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.working_memory import WorkingMemoryStore


@lru_cache(maxsize=1)
def get_config() -> KnowledgeMemoryConfig:
    """Return the cached service configuration."""
    return KnowledgeMemoryConfig()


_knowledge_store: KnowledgeStore | None = None
_working_memory: WorkingMemoryStore | None = None
_heuristic_engine: HeuristicEngine | None = None


def get_knowledge_store() -> KnowledgeStore:
    """Return the shared :class:`KnowledgeStore` instance."""
    if _knowledge_store is None:
        msg = "KnowledgeStore not initialized. Service lifespan has not started."
        raise RuntimeError(msg)
    return _knowledge_store


def set_knowledge_store(store: KnowledgeStore) -> None:
    """Set the shared :class:`KnowledgeStore` instance."""
    global _knowledge_store
    _knowledge_store = store


def get_working_memory() -> WorkingMemoryStore:
    """Return the shared :class:`WorkingMemoryStore` instance."""
    if _working_memory is None:
        msg = "WorkingMemoryStore not initialized. Service lifespan has not started."
        raise RuntimeError(msg)
    return _working_memory


def set_working_memory(store: WorkingMemoryStore) -> None:
    """Set the shared :class:`WorkingMemoryStore` instance."""
    global _working_memory
    _working_memory = store


def get_heuristic_engine() -> HeuristicEngine:
    """Return the shared :class:`HeuristicEngine` instance."""
    if _heuristic_engine is None:
        msg = "HeuristicEngine not initialized. Service lifespan has not started."
        raise RuntimeError(msg)
    return _heuristic_engine


def set_heuristic_engine(engine: HeuristicEngine) -> None:
    """Set the shared :class:`HeuristicEngine` instance."""
    global _heuristic_engine
    _heuristic_engine = engine


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _knowledge_store, _working_memory, _heuristic_engine
    _knowledge_store = None
    _working_memory = None
    _heuristic_engine = None
