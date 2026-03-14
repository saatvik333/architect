"""Tests for the AST indexer."""

from __future__ import annotations

from codebase_comprehension.ast_indexer import ASTIndexer

# -- Sample source snippets (inline to avoid conftest import issues) ----------

SIMPLE_FUNCTION_SRC = """\
def greet(name: str) -> str:
    \"\"\"Return a greeting.\"\"\"
    return f"Hello, {name}!"
"""

CLASS_WITH_METHODS_SRC = """\
class Calculator:
    \"\"\"A simple calculator.\"\"\"

    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
"""

ASYNC_FUNCTION_SRC = """\
async def fetch_data(url: str) -> dict:
    \"\"\"Fetch data from a URL.\"\"\"
    return {"url": url}
"""

DECORATED_FUNCTION_SRC = """\
import functools

def my_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@my_decorator
def decorated_func(x: int) -> int:
    return x * 2
"""

IMPORTS_SRC = """\
import os
import sys
from pathlib import Path
from . import utils
from ..core import base
"""

EMPTY_FILE_SRC = ""

SYNTAX_ERROR_SRC = """\
def broken(
    # missing closing paren and colon
"""

NESTED_CLASS_SRC = """\
class Outer:
    class Inner:
        def inner_method(self) -> None:
            pass

    def outer_method(self) -> None:
        pass
"""

MODULE_VARIABLES_SRC = """\
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0

def process() -> None:
    pass
"""

RELATIVE_IMPORT_SRC = """\
from . import models
from ..utils import helpers
"""


class TestIndexFile:
    """Tests for ASTIndexer.index_file()."""

    def test_parse_simple_function(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", SIMPLE_FUNCTION_SRC)

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "greet"
        assert func.parameters == ["name"]
        assert func.return_type == "str"
        assert func.docstring == "Return a greeting."
        assert func.is_async is False
        assert func.line_number == 1

    def test_parse_class_with_methods(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", CLASS_WITH_METHODS_SRC)

        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Calculator"
        assert cls.docstring == "A simple calculator."
        assert len(cls.methods) == 2
        assert cls.methods[0].name == "add"
        assert cls.methods[1].name == "subtract"

    def test_parse_async_function(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", ASYNC_FUNCTION_SRC)

        assert len(result.functions) == 1
        func = result.functions[0]
        assert func.name == "fetch_data"
        assert func.is_async is True
        assert func.return_type == "dict"
        assert func.docstring == "Fetch data from a URL."

    def test_parse_decorated_function(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", DECORATED_FUNCTION_SRC)

        # Top-level: my_decorator, decorated_func
        decorated = [f for f in result.functions if f.name == "decorated_func"]
        assert len(decorated) == 1
        assert "my_decorator" in decorated[0].decorators

    def test_parse_imports(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", IMPORTS_SRC)

        assert len(result.imports) >= 4
        modules = [imp.module for imp in result.imports]
        assert "os" in modules
        assert "sys" in modules
        assert "pathlib" in modules

    def test_parse_relative_imports(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", RELATIVE_IMPORT_SRC)

        relative_imports = [imp for imp in result.imports if imp.is_relative]
        assert len(relative_imports) == 2

    def test_parse_empty_file(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("empty.py", EMPTY_FILE_SRC)

        assert result.path == "empty.py"
        assert len(result.functions) == 0
        assert len(result.classes) == 0
        assert len(result.imports) == 0

    def test_syntax_error_returns_empty_index(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("broken.py", SYNTAX_ERROR_SRC)

        assert result.path == "broken.py"
        assert len(result.functions) == 0
        assert len(result.classes) == 0
        assert len(result.imports) == 0

    def test_nested_classes(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", NESTED_CLASS_SRC)

        # Only top-level class Outer should appear
        assert len(result.classes) == 1
        outer = result.classes[0]
        assert outer.name == "Outer"
        # outer_method is a direct child method
        method_names = [m.name for m in outer.methods]
        assert "outer_method" in method_names

    def test_module_level_variables(self, ast_indexer: ASTIndexer) -> None:
        result = ast_indexer.index_file("test.py", MODULE_VARIABLES_SRC)

        # Variables are not extracted as functions/classes, but the file still indexes
        assert result.path == "test.py"
        assert len(result.functions) == 1
        assert result.functions[0].name == "process"
        # Line count should be correct
        assert result.line_count == MODULE_VARIABLES_SRC.count("\n") + 1
