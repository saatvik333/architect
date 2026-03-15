"""Tests for the SemanticChunker."""

from __future__ import annotations

import pytest

from codebase_comprehension.chunker import SemanticChunker
from codebase_comprehension.models import ClassDef, FileIndex, FunctionDef


@pytest.fixture
def chunker() -> SemanticChunker:
    """Return a fresh SemanticChunker with default settings."""
    return SemanticChunker()


@pytest.fixture
def small_chunker() -> SemanticChunker:
    """Return a SemanticChunker with a very small max_tokens for truncation tests."""
    return SemanticChunker(max_tokens=10)  # ~40 chars


SOURCE_WITH_FUNCTIONS = """\
# A helper module

def greet(name: str) -> str:
    \"\"\"Say hello.\"\"\"
    return f"Hello, {name}!"

def farewell(name: str) -> str:
    return f"Goodbye, {name}!"
"""


SOURCE_WITH_CLASS = """\
class Calculator:
    \"\"\"A simple calculator.\"\"\"

    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
"""


class TestSymbolLevelChunking:
    """Test that chunks correspond to individual symbols."""

    def test_functions_produce_chunks(self, chunker: SemanticChunker) -> None:
        file_index = FileIndex(
            path="helpers.py",
            functions=[
                FunctionDef(
                    name="greet",
                    file_path="helpers.py",
                    line_number=3,
                    parameters=["name"],
                    return_type="str",
                ),
                FunctionDef(
                    name="farewell",
                    file_path="helpers.py",
                    line_number=7,
                    parameters=["name"],
                    return_type="str",
                ),
            ],
        )
        chunks = chunker.chunk_file(SOURCE_WITH_FUNCTIONS, file_index)

        assert len(chunks) == 2
        assert chunks[0].symbol_name == "greet"
        assert chunks[0].symbol_kind == "function"
        assert chunks[0].line_number == 3
        assert chunks[1].symbol_name == "farewell"

    def test_class_and_methods_produce_chunks(self, chunker: SemanticChunker) -> None:
        file_index = FileIndex(
            path="calc.py",
            classes=[
                ClassDef(
                    name="Calculator",
                    file_path="calc.py",
                    line_number=1,
                    methods=[
                        FunctionDef(
                            name="add",
                            file_path="calc.py",
                            line_number=4,
                            parameters=["self", "a", "b"],
                        ),
                        FunctionDef(
                            name="subtract",
                            file_path="calc.py",
                            line_number=7,
                            parameters=["self", "a", "b"],
                        ),
                    ],
                )
            ],
        )
        chunks = chunker.chunk_file(SOURCE_WITH_CLASS, file_index)

        # 1 class chunk + 2 method chunks
        assert len(chunks) == 3
        names = {c.symbol_name for c in chunks}
        assert "Calculator" in names
        assert "Calculator.add" in names
        assert "Calculator.subtract" in names


class TestMaxTokens:
    """Test chunk truncation when exceeding max_tokens."""

    def test_long_source_truncated(self, small_chunker: SemanticChunker) -> None:
        long_source = "def big_func():\n" + "    x = 1\n" * 100
        file_index = FileIndex(
            path="big.py",
            functions=[
                FunctionDef(name="big_func", file_path="big.py", line_number=1),
            ],
        )
        chunks = small_chunker.chunk_file(long_source, file_index)

        assert len(chunks) == 1
        assert "truncated" in chunks[0].source


class TestEmptyFile:
    """Test chunking with no symbols."""

    def test_empty_file_produces_no_chunks(self, chunker: SemanticChunker) -> None:
        file_index = FileIndex(path="empty.py", line_count=0)
        chunks = chunker.chunk_file("", file_index)
        assert chunks == []
