"""ARCHITECT Codebase Comprehension — AST-based code indexing and context assembly."""

from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.call_graph import CallGraphBuilder
from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.convention_extractor import ConventionExtractor
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import (
    ClassDef,
    CodebaseIndex,
    CodeContext,
    ConventionReport,
    FileIndex,
    FunctionDef,
    ImportInfo,
    SymbolInfo,
)

__all__ = [
    "ASTIndexer",
    "CallGraphBuilder",
    "ClassDef",
    "CodeContext",
    "CodebaseIndex",
    "ContextAssembler",
    "ConventionExtractor",
    "ConventionReport",
    "FileIndex",
    "FunctionDef",
    "ImportInfo",
    "IndexStore",
    "SymbolInfo",
]
