"""AST-based code indexer using Python's built-in ast module."""

from __future__ import annotations

import ast
import pathlib

import structlog

from codebase_comprehension.models import (
    ClassDef,
    CodebaseIndex,
    FileIndex,
    FunctionDef,
    ImportInfo,
)

logger = structlog.get_logger()


class ASTIndexer:
    """Parse Python source files and build a structured index of their symbols."""

    def index_file(self, file_path: str, source: str) -> FileIndex:
        """Parse *source* with ``ast.parse()`` and extract functions, classes, imports.

        Returns an empty :class:`FileIndex` on :class:`SyntaxError`.
        """
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            logger.warning("syntax_error", file_path=file_path)
            return FileIndex(path=file_path, line_count=source.count("\n") + 1)

        functions = self._extract_functions(tree, file_path)
        classes = self._extract_classes(tree, file_path)
        imports = self._extract_imports(tree, file_path)
        line_count = source.count("\n") + 1

        return FileIndex(
            path=file_path,
            functions=functions,
            classes=classes,
            imports=imports,
            line_count=line_count,
        )

    def index_directory(
        self,
        directory: str,
        glob_pattern: str = "**/*.py",
        *,
        max_files: int = 10000,
    ) -> CodebaseIndex:
        """Walk *directory*, read each ``.py`` file, and build a :class:`CodebaseIndex`."""
        root = pathlib.Path(directory).resolve()
        if not root.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        # Reject patterns that could escape the root via absolute paths or traversal.
        if pathlib.PurePosixPath(glob_pattern).is_absolute() or ".." in glob_pattern:
            raise ValueError(f"Invalid glob pattern: {glob_pattern}")

        files: dict[str, FileIndex] = {}
        total_symbols = 0

        for py_file in sorted(root.glob(glob_pattern)):
            if len(files) >= max_files:
                break
            if not py_file.is_file():
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                logger.warning("read_error", file_path=str(py_file))
                continue

            rel_path = str(py_file.relative_to(root))
            file_index = self.index_file(rel_path, source)
            files[rel_path] = file_index
            total_symbols += (
                len(file_index.functions) + len(file_index.classes) + len(file_index.imports)
            )

        return CodebaseIndex(
            root_path=directory,
            files=files,
            total_files=len(files),
            total_symbols=total_symbols,
        )

    # -- Private helpers ----------------------------------------------------

    def _extract_functions(self, tree: ast.Module, file_path: str) -> list[FunctionDef]:
        """Extract top-level function and async-function definitions."""
        results: list[FunctionDef] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results.append(self._parse_function(node, file_path))
        return results

    def _extract_classes(self, tree: ast.Module, file_path: str) -> list[ClassDef]:
        """Extract class definitions (including nested methods)."""
        results: list[ClassDef] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                results.append(self._parse_class(node, file_path))
        return results

    def _extract_imports(self, tree: ast.Module, file_path: str) -> list[ImportInfo]:
        """Extract ``import`` and ``from … import`` statements."""
        results: list[ImportInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    results.append(
                        ImportInfo(
                            module=alias.name,
                            names=[alias.asname or alias.name],
                            is_relative=False,
                            file_path=file_path,
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                names = [alias.name for alias in node.names]
                results.append(
                    ImportInfo(
                        module=module_name,
                        names=names,
                        is_relative=node.level > 0,
                        file_path=file_path,
                        line_number=node.lineno,
                    )
                )
        return results

    # -- Node parsers -------------------------------------------------------

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
    ) -> FunctionDef:
        """Convert an AST function node into a :class:`FunctionDef`."""
        parameters = [arg.arg for arg in node.args.args]
        return_type = ""
        if node.returns is not None:
            return_type = ast.unparse(node.returns)

        decorators = [ast.unparse(d) for d in node.decorator_list]
        calls = self._extract_calls(node)
        docstring = ast.get_docstring(node) or ""

        return FunctionDef(
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            parameters=parameters,
            return_type=return_type,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            calls=calls,
            docstring=docstring,
        )

    def _parse_class(self, node: ast.ClassDef, file_path: str) -> ClassDef:
        """Convert an AST class node into a :class:`ClassDef`."""
        bases = [ast.unparse(b) for b in node.bases]
        methods: list[FunctionDef] = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_function(child, file_path))

        docstring = ast.get_docstring(node) or ""

        return ClassDef(
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            bases=bases,
            methods=methods,
            docstring=docstring,
        )

    def _extract_calls(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        """Walk the function body and extract names of called functions."""
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._resolve_call_name(child.func)
                if call_name:
                    calls.append(call_name)
        return calls

    @staticmethod
    def _resolve_call_name(node: ast.expr) -> str:
        """Resolve a Call node's function to a dotted name string."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = ASTIndexer._resolve_call_name(node.value)
            if prefix:
                return f"{prefix}.{node.attr}"
            return node.attr
        return ""
