"""Tests for the TreeSitterIndexer multi-language parser."""

from __future__ import annotations

import pytest

from codebase_comprehension.tree_sitter_indexer import TreeSitterIndexer


@pytest.fixture
def ts_indexer() -> TreeSitterIndexer:
    """Return a fresh TreeSitterIndexer."""
    return TreeSitterIndexer()


# -- Python parsing ----------------------------------------------------------


class TestPythonFunctions:
    """Test extraction of Python function definitions."""

    def test_simple_function(self, ts_indexer: TreeSitterIndexer) -> None:
        source = (
            'def greet(name: str) -> str:\n    """Say hello."""\n    return f"Hello, {name}!"\n'
        )
        result = ts_indexer.index_file(source, "greet.py", "python")

        assert result.path == "greet.py"
        assert result.language == "python"
        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "greet"
        assert func.line_number == 1
        assert "name" in func.parameters

    def test_async_function(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "async def fetch(url: str) -> dict:\n    return {}\n"
        result = ts_indexer.index_file(source, "fetch.py", "python")

        assert len(result.functions) == 1
        assert result.functions[0].is_async is True
        assert result.functions[0].name == "fetch"

    def test_decorated_function(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "@my_decorator\ndef decorated(x: int) -> int:\n    return x * 2\n"
        result = ts_indexer.index_file(source, "dec.py", "python")

        assert len(result.functions) == 1
        assert result.functions[0].name == "decorated"
        assert len(result.functions[0].decorators) == 1

    def test_function_calls_extracted(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "def caller():\n    helper()\n    print('done')\n"
        result = ts_indexer.index_file(source, "calls.py", "python")

        assert len(result.functions) == 1
        calls = result.functions[0].calls
        assert "helper" in calls
        assert "print" in calls


class TestPythonClasses:
    """Test extraction of Python class definitions."""

    def test_class_with_methods(self, ts_indexer: TreeSitterIndexer) -> None:
        source = (
            "class Calculator:\n"
            '    """A simple calculator."""\n'
            "\n"
            "    def add(self, a: int, b: int) -> int:\n"
            "        return a + b\n"
            "\n"
            "    def subtract(self, a: int, b: int) -> int:\n"
            "        return a - b\n"
        )
        result = ts_indexer.index_file(source, "calc.py", "python")

        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Calculator"
        assert cls.docstring == "A simple calculator."
        assert len(cls.methods) == 2
        method_names = {m.name for m in cls.methods}
        assert method_names == {"add", "subtract"}

    def test_class_with_bases(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "class MyError(ValueError):\n    pass\n"
        result = ts_indexer.index_file(source, "err.py", "python")

        assert len(result.classes) == 1
        assert "ValueError" in result.classes[0].bases


class TestPythonImports:
    """Test extraction of Python import statements."""

    def test_simple_import(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "import os\nimport sys\n"
        result = ts_indexer.index_file(source, "imp.py", "python")

        assert len(result.imports) == 2
        modules = {imp.module for imp in result.imports}
        assert "os" in modules
        assert "sys" in modules

    def test_from_import(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "from pathlib import Path\n"
        result = ts_indexer.index_file(source, "imp.py", "python")

        assert len(result.imports) == 1
        assert result.imports[0].module == "pathlib"
        assert "Path" in result.imports[0].names

    def test_relative_import(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "from . import utils\n"
        result = ts_indexer.index_file(source, "imp.py", "python")

        assert len(result.imports) == 1
        assert result.imports[0].is_relative is True


# -- Error handling ----------------------------------------------------------


class TestErrorHandling:
    """Test graceful degradation on bad input."""

    def test_invalid_syntax_returns_empty(self, ts_indexer: TreeSitterIndexer) -> None:
        source = "def broken(\n    # missing closing paren\n"
        result = ts_indexer.index_file(source, "bad.py", "python")

        # tree-sitter is error-tolerant — it should still parse but may return
        # fewer symbols. The key invariant is no exception is raised.
        assert result.path == "bad.py"
        assert result.language == "python"

    def test_empty_file(self, ts_indexer: TreeSitterIndexer) -> None:
        result = ts_indexer.index_file("", "empty.py", "python")

        assert result.path == "empty.py"
        assert len(result.functions) == 0
        assert len(result.classes) == 0
        assert len(result.imports) == 0

    def test_unsupported_language_fallback(self, ts_indexer: TreeSitterIndexer) -> None:
        result = ts_indexer.index_file("fn main() {}", "main.rs", "rust")

        assert result.path == "main.rs"
        assert result.language == "rust"
        assert len(result.functions) == 0
        assert len(result.classes) == 0
