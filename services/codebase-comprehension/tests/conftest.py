"""Shared pytest fixtures for codebase-comprehension tests."""

from __future__ import annotations

import pytest

from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import CodebaseIndex, FileIndex, FunctionDef

# -- Sample Python source snippets ------------------------------------------

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

CALL_CHAIN_SRC = """\
def helper():
    pass

def caller():
    helper()
    print("done")
"""

CROSS_FILE_A_SRC = """\
def func_a():
    func_b()
"""

CROSS_FILE_B_SRC = """\
def func_b():
    pass
"""

METHOD_CALLS_SRC = """\
class Service:
    def handle(self):
        self.validate()
        self.process()

    def validate(self):
        pass

    def process(self):
        pass
"""

CONVENTION_SRC = """\
class MyService:
    \"\"\"A well-named service.\"\"\"

    async def get_items(self) -> list:
        return []

    @staticmethod
    def compute_total(items: list) -> int:
        return sum(items)

def parse_input(raw: str) -> dict:
    return {}
"""

RELATIVE_IMPORT_SRC = """\
from . import models
from ..utils import helpers
"""


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def ast_indexer() -> ASTIndexer:
    """Return a fresh ASTIndexer."""
    return ASTIndexer()


@pytest.fixture
def index_store() -> IndexStore:
    """Return a fresh IndexStore."""
    return IndexStore()


@pytest.fixture
def sample_codebase_index(ast_indexer: ASTIndexer) -> CodebaseIndex:
    """Return a CodebaseIndex with several sample files."""
    files: dict[str, FileIndex] = {}

    files["src/greet.py"] = ast_indexer.index_file("src/greet.py", SIMPLE_FUNCTION_SRC)
    files["src/calc.py"] = ast_indexer.index_file("src/calc.py", CLASS_WITH_METHODS_SRC)
    files["src/fetch.py"] = ast_indexer.index_file("src/fetch.py", ASYNC_FUNCTION_SRC)
    files["src/service.py"] = ast_indexer.index_file("src/service.py", CONVENTION_SRC)
    files["tests/test_greet.py"] = ast_indexer.index_file(
        "tests/test_greet.py",
        'def test_greet():\n    assert greet("World") == "Hello, World!"\n',
    )
    files["tests/test_calc.py"] = ast_indexer.index_file(
        "tests/test_calc.py",
        "def test_add():\n    pass\n",
    )

    total_symbols = sum(
        len(fi.functions) + len(fi.classes) + len(fi.imports) for fi in files.values()
    )

    return CodebaseIndex(
        root_path="/project",
        files=files,
        total_files=len(files),
        total_symbols=total_symbols,
    )


@pytest.fixture
def populated_store(index_store: IndexStore, sample_codebase_index: CodebaseIndex) -> IndexStore:
    """Return an IndexStore with the sample codebase index stored."""
    index_store.store(sample_codebase_index)
    return index_store


@pytest.fixture
def call_chain_index(ast_indexer: ASTIndexer) -> CodebaseIndex:
    """Return a CodebaseIndex for call-graph testing."""
    files: dict[str, FileIndex] = {}
    files["main.py"] = ast_indexer.index_file("main.py", CALL_CHAIN_SRC)
    files["a.py"] = ast_indexer.index_file("a.py", CROSS_FILE_A_SRC)
    files["b.py"] = ast_indexer.index_file("b.py", CROSS_FILE_B_SRC)
    files["service.py"] = ast_indexer.index_file("service.py", METHOD_CALLS_SRC)

    total_symbols = sum(
        len(fi.functions) + len(fi.classes) + len(fi.imports) for fi in files.values()
    )

    return CodebaseIndex(
        root_path="/project",
        files=files,
        total_files=len(files),
        total_symbols=total_symbols,
    )


@pytest.fixture
def sample_function_def() -> FunctionDef:
    """Return a simple FunctionDef for testing."""
    return FunctionDef(
        name="greet",
        file_path="src/greet.py",
        line_number=1,
        parameters=["name"],
        return_type="str",
        docstring="Return a greeting.",
    )
