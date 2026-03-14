"""Convention extractor that analyses a CodebaseIndex for coding patterns."""

from __future__ import annotations

import re

from codebase_comprehension.models import CodebaseIndex, ConventionReport


class ConventionExtractor:
    """Detect naming conventions, file organisation, and common patterns."""

    def extract(self, index: CodebaseIndex) -> ConventionReport:
        """Analyse *index* and return a :class:`ConventionReport`."""
        naming_patterns = self._detect_naming(index)
        file_organization = self._detect_file_organization(index)
        common_patterns = self._detect_common_patterns(index)
        test_patterns = self._detect_test_patterns(index)

        return ConventionReport(
            naming_patterns=naming_patterns,
            file_organization=file_organization,
            common_patterns=common_patterns,
            test_patterns=test_patterns,
        )

    # -- Private helpers ----------------------------------------------------

    @staticmethod
    def _detect_naming(index: CodebaseIndex) -> dict[str, str]:
        """Detect naming conventions for functions and classes."""
        snake_funcs = 0
        total_funcs = 0
        pascal_classes = 0
        total_classes = 0

        for file_index in index.files.values():
            for func in file_index.functions:
                total_funcs += 1
                if re.match(r"^[a-z_][a-z0-9_]*$", func.name):
                    snake_funcs += 1
            for cls in file_index.classes:
                total_classes += 1
                if re.match(r"^[A-Z][a-zA-Z0-9]*$", cls.name):
                    pascal_classes += 1
                for method in cls.methods:
                    total_funcs += 1
                    if re.match(r"^[a-z_][a-z0-9_]*$", method.name):
                        snake_funcs += 1

        patterns: dict[str, str] = {}
        if total_funcs > 0:
            pct = snake_funcs * 100 // total_funcs
            patterns["functions"] = f"snake_case ({pct}%)"
        if total_classes > 0:
            pct = pascal_classes * 100 // total_classes
            patterns["classes"] = f"PascalCase ({pct}%)"
        return patterns

    @staticmethod
    def _detect_file_organization(index: CodebaseIndex) -> list[str]:
        """Detect directory structure patterns."""
        dirs: set[str] = set()
        for path in index.files:
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 1:
                dirs.add(parts[0])

        known = {
            "api": "api/ — API routes",
            "temporal": "temporal/ — Temporal workflows",
            "tests": "tests/ — test files",
            "src": "src/ — source package",
            "models": "models/ — data models",
        }
        return [known[d] for d in sorted(dirs) if d in known]

    @staticmethod
    def _detect_common_patterns(index: CodebaseIndex) -> list[str]:
        """Detect common coding patterns (async, decorators, etc.)."""
        patterns: list[str] = []
        async_count = 0
        decorator_count = 0
        total_funcs = 0

        for file_index in index.files.values():
            for func in file_index.functions:
                total_funcs += 1
                if func.is_async:
                    async_count += 1
                if func.decorators:
                    decorator_count += 1
            for cls in file_index.classes:
                for method in cls.methods:
                    total_funcs += 1
                    if method.is_async:
                        async_count += 1
                    if method.decorators:
                        decorator_count += 1

        if async_count > 0:
            patterns.append(f"async/await ({async_count} async functions)")
        if decorator_count > 0:
            patterns.append(f"decorators ({decorator_count} decorated functions)")
        return patterns

    @staticmethod
    def _detect_test_patterns(index: CodebaseIndex) -> list[str]:
        """Detect test file and naming patterns."""
        patterns: list[str] = []
        test_files = [p for p in index.files if "test_" in p or p.endswith("_test.py")]
        if test_files:
            patterns.append(f"test files: {len(test_files)} (test_*.py / *_test.py)")

        # Check for pytest fixtures
        conftest_files = [p for p in index.files if p.endswith("conftest.py")]
        if conftest_files:
            patterns.append(f"conftest.py files: {len(conftest_files)}")

        return patterns
