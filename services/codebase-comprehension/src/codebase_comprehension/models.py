"""Pydantic domain models for Codebase Comprehension."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from architect_common.types import ArchitectBase, utcnow


class SymbolInfo(ArchitectBase):
    """A single symbol (function, class, method, variable, or import) in the codebase."""

    name: str
    kind: Literal["function", "class", "method", "variable", "import"]
    file_path: str
    line_number: int
    end_line_number: int | None = None
    docstring: str = ""
    decorators: list[str] = Field(default_factory=list)


class FunctionDef(ArchitectBase):
    """A function or method definition extracted from the AST."""

    name: str
    file_path: str
    line_number: int
    parameters: list[str] = Field(default_factory=list)
    return_type: str = ""
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)
    docstring: str = ""


class ClassDef(ArchitectBase):
    """A class definition extracted from the AST."""

    name: str
    file_path: str
    line_number: int
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionDef] = Field(default_factory=list)
    docstring: str = ""


class ImportInfo(ArchitectBase):
    """An import statement extracted from the AST."""

    module: str
    names: list[str] = Field(default_factory=list)
    is_relative: bool = False
    file_path: str = ""
    line_number: int = 0


class FileIndex(ArchitectBase):
    """Index of all symbols in a single file."""

    path: str
    language: str = "python"
    functions: list[FunctionDef] = Field(default_factory=list)
    classes: list[ClassDef] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    line_count: int = 0


class CodebaseIndex(ArchitectBase):
    """Index of all symbols across a codebase directory."""

    root_path: str
    files: dict[str, FileIndex] = Field(default_factory=dict)
    total_files: int = 0
    total_symbols: int = 0
    indexed_at: datetime = Field(default_factory=utcnow)


class CodeContext(ArchitectBase):
    """Assembled context for a coding task, based on codebase analysis."""

    relevant_files: list[str] = Field(default_factory=list)
    file_chunks: dict[str, str] = Field(default_factory=dict)
    related_symbols: list[SymbolInfo] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    import_graph: dict[str, list[str]] = Field(default_factory=dict)


class CodeChunk(ArchitectBase):
    """A semantic chunk of source code, typically a function/class/method body."""

    file_path: str
    symbol_name: str
    symbol_kind: str
    line_number: int
    end_line: int
    source: str
    context: str = ""


class EmbeddingResult(ArchitectBase):
    """A search result from the vector store with similarity score."""

    symbol_name: str
    symbol_kind: str
    file_path: str
    line_number: int
    source_chunk: str
    score: float
    metadata: dict[str, str] = Field(default_factory=dict)


class ArchitectureMap(ArchitectBase):
    """High-level architecture map of a codebase."""

    modules: dict[str, list[str]] = Field(default_factory=dict)
    entry_points: list[str] = Field(default_factory=list)
    layers: dict[str, list[str]] = Field(default_factory=dict)


class ConventionReport(ArchitectBase):
    """Report of coding conventions detected in a codebase."""

    naming_patterns: dict[str, str] = Field(default_factory=dict)
    file_organization: list[str] = Field(default_factory=list)
    common_patterns: list[str] = Field(default_factory=list)
    test_patterns: list[str] = Field(default_factory=list)
