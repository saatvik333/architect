"""FastAPI dependency injection for Codebase Comprehension."""

from __future__ import annotations

from functools import lru_cache

from codebase_comprehension.architecture_map import ArchitectureMapGenerator
from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.config import CodebaseComprehensionConfig
from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.index_store import IndexStore


@lru_cache(maxsize=1)
def get_config() -> CodebaseComprehensionConfig:
    """Return the cached service configuration."""
    return CodebaseComprehensionConfig()


_index_store: IndexStore | None = None
_ast_indexer: ASTIndexer | None = None
_context_assembler: ContextAssembler | None = None
_architecture_map_generator: ArchitectureMapGenerator | None = None


def get_index_store() -> IndexStore:
    """Return a shared :class:`IndexStore` instance."""
    global _index_store
    if _index_store is None:
        _index_store = IndexStore()
    return _index_store


def get_ast_indexer() -> ASTIndexer:
    """Return a shared :class:`ASTIndexer` instance."""
    global _ast_indexer
    if _ast_indexer is None:
        _ast_indexer = ASTIndexer()
    return _ast_indexer


def get_context_assembler() -> ContextAssembler:
    """Return a shared :class:`ContextAssembler` instance."""
    global _context_assembler
    if _context_assembler is None:
        _context_assembler = ContextAssembler(index_store=get_index_store())
    return _context_assembler


def get_architecture_map_generator() -> ArchitectureMapGenerator:
    """Return a shared :class:`ArchitectureMapGenerator` instance."""
    global _architecture_map_generator
    if _architecture_map_generator is None:
        _architecture_map_generator = ArchitectureMapGenerator()
    return _architecture_map_generator


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _index_store, _ast_indexer, _context_assembler, _architecture_map_generator
    _index_store = None
    _ast_indexer = None
    _context_assembler = None
    _architecture_map_generator = None
