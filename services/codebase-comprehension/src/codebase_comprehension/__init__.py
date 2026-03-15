"""ARCHITECT Codebase Comprehension — multi-language code indexing, semantic search, and context assembly."""

from codebase_comprehension.architecture_map import ArchitectureMapGenerator
from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.call_graph import CallGraphBuilder
from codebase_comprehension.chunker import SemanticChunker
from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.convention_extractor import ConventionExtractor
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import (
    ArchitectureMap,
    ClassDef,
    CodebaseIndex,
    CodeChunk,
    CodeContext,
    ConventionReport,
    EmbeddingResult,
    FileIndex,
    FunctionDef,
    ImportInfo,
    SymbolInfo,
)
from codebase_comprehension.tree_sitter_indexer import TreeSitterIndexer

__all__ = [
    "ASTIndexer",
    "ArchitectureMap",
    "ArchitectureMapGenerator",
    "CallGraphBuilder",
    "ClassDef",
    "CodeChunk",
    "CodeContext",
    "CodebaseIndex",
    "ContextAssembler",
    "ConventionExtractor",
    "ConventionReport",
    "EmbeddingResult",
    "FileIndex",
    "FunctionDef",
    "ImportInfo",
    "IndexStore",
    "SemanticChunker",
    "SymbolInfo",
    "TreeSitterIndexer",
]
