"""Call-graph builder from a CodebaseIndex."""

from __future__ import annotations

from codebase_comprehension.models import CodebaseIndex


class CallGraphBuilder:
    """Build a caller/callee graph from function definitions in a :class:`CodebaseIndex`."""

    def __init__(self) -> None:
        self._graph: dict[str, list[str]] = {}  # caller -> [callees]
        self._reverse: dict[str, list[str]] = {}  # callee -> [callers]

    def build(self, index: CodebaseIndex) -> dict[str, list[str]]:
        """Build the call graph from all functions in *index*.

        Key format: ``"file_path::function_name"``.

        Returns the forward graph (caller -> callees).
        """
        self._graph = {}
        self._reverse = {}

        for file_path, file_index in index.files.items():
            # Top-level functions
            for func in file_index.functions:
                caller_key = f"{file_path}::{func.name}"
                callees = list(func.calls)
                self._graph[caller_key] = callees
                for callee in callees:
                    self._reverse.setdefault(callee, []).append(caller_key)

            # Class methods
            for cls in file_index.classes:
                for method in cls.methods:
                    caller_key = f"{file_path}::{cls.name}.{method.name}"
                    callees = list(method.calls)
                    self._graph[caller_key] = callees
                    for callee in callees:
                        self._reverse.setdefault(callee, []).append(caller_key)

        return dict(self._graph)

    def get_callers(self, function_name: str) -> list[str]:
        """Return all callers of *function_name*."""
        return list(self._reverse.get(function_name, []))

    def get_callees(self, function_name: str) -> list[str]:
        """Return all callees of *function_name*."""
        return list(self._graph.get(function_name, []))
