"""In-memory store for codebase indices."""

from __future__ import annotations

from collections import OrderedDict

from codebase_comprehension.models import CodebaseIndex, SymbolInfo

MAX_INDICES = 50
"""Maximum number of indices kept in memory before evicting the oldest."""


class IndexStore:
    """In-memory store for :class:`CodebaseIndex` instances, keyed by root path."""

    def __init__(self) -> None:
        self._indices: OrderedDict[str, CodebaseIndex] = OrderedDict()

    def store(self, index: CodebaseIndex) -> None:
        """Store *index* keyed by its ``root_path``.

        If the store already holds :data:`MAX_INDICES` entries, the oldest
        entry is evicted to make room.
        """
        # Move to end if already present (refresh recency)
        if index.root_path in self._indices:
            self._indices.move_to_end(index.root_path)
        elif len(self._indices) >= MAX_INDICES:
            self._indices.popitem(last=False)
        self._indices[index.root_path] = index

    def get(self, root_path: str) -> CodebaseIndex | None:
        """Return the index for *root_path*, or ``None``."""
        return self._indices.get(root_path)

    def search_symbols(self, query: str, limit: int = 20) -> list[SymbolInfo]:
        """Search all stored indices for symbols matching *query*.

        Case-insensitive substring match on symbol names.
        """
        query_lower = query.lower()
        results: list[SymbolInfo] = []

        for index in self._indices.values():
            for file_path, file_index in index.files.items():
                for func in file_index.functions:
                    if query_lower in func.name.lower():
                        results.append(
                            SymbolInfo(
                                name=func.name,
                                kind="function",
                                file_path=file_path,
                                line_number=func.line_number,
                                docstring=func.docstring,
                                decorators=func.decorators,
                            )
                        )
                        if len(results) >= limit:
                            return results

                for cls in file_index.classes:
                    if query_lower in cls.name.lower():
                        results.append(
                            SymbolInfo(
                                name=cls.name,
                                kind="class",
                                file_path=file_path,
                                line_number=cls.line_number,
                                docstring=cls.docstring,
                            )
                        )
                        if len(results) >= limit:
                            return results

                    for method in cls.methods:
                        if query_lower in method.name.lower():
                            results.append(
                                SymbolInfo(
                                    name=f"{cls.name}.{method.name}",
                                    kind="method",
                                    file_path=file_path,
                                    line_number=method.line_number,
                                    docstring=method.docstring,
                                    decorators=method.decorators,
                                )
                            )
                            if len(results) >= limit:
                                return results

        return results
