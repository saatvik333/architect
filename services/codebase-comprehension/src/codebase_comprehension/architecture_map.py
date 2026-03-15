"""Architecture map generator that builds high-level views of a codebase."""

from __future__ import annotations

import pathlib
from typing import ClassVar

from codebase_comprehension.models import ArchitectureMap, CodebaseIndex


class ArchitectureMapGenerator:
    """Analyse a :class:`CodebaseIndex` and produce an :class:`ArchitectureMap`.

    Extracts module-level dependency information, identifies entry points,
    and groups modules into conventional layers.
    """

    # Known layer patterns (directory name -> layer name)
    _LAYER_PATTERNS: ClassVar[dict[str, str]] = {
        "api": "api",
        "routes": "api",
        "models": "models",
        "schemas": "models",
        "services": "services",
        "service": "services",
        "core": "services",
        "utils": "utils",
        "helpers": "utils",
        "lib": "utils",
        "tests": "tests",
        "test": "tests",
        "temporal": "temporal",
        "workflows": "temporal",
    }

    def generate(self, index: CodebaseIndex) -> ArchitectureMap:
        """Build an :class:`ArchitectureMap` from *index*."""
        modules = self._build_module_deps(index)
        entry_points = self._find_entry_points(index)
        layers = self._classify_layers(index)

        return ArchitectureMap(
            modules=modules,
            entry_points=entry_points,
            layers=layers,
        )

    def _build_module_deps(self, index: CodebaseIndex) -> dict[str, list[str]]:
        """Build a module -> [dependency modules] mapping from import data."""
        modules: dict[str, list[str]] = {}

        for file_path, file_index in index.files.items():
            module_name = self._path_to_module(file_path)
            deps: list[str] = []
            for imp in file_index.imports:
                if imp.module and not imp.is_relative:
                    deps.append(imp.module)
                elif imp.module and imp.is_relative:
                    deps.append(f".{imp.module}" if imp.module else ".")
            modules[module_name] = sorted(set(deps))

        return modules

    def _find_entry_points(self, index: CodebaseIndex) -> list[str]:
        """Identify files that look like entry points."""
        entry_points: list[str] = []

        for file_path, file_index in index.files.items():
            # Files with __main__ pattern
            if file_path.endswith("__main__.py"):
                entry_points.append(file_path)
                continue

            # Files containing 'if __name__' or app factory patterns
            for func in file_index.functions:
                if func.name in ("main", "create_app", "app"):
                    entry_points.append(file_path)
                    break

            # Files named main.py, app.py, cli.py, service.py
            stem = pathlib.PurePosixPath(file_path).stem
            if stem in ("main", "app", "cli", "service") and file_path not in entry_points:
                entry_points.append(file_path)

        return sorted(set(entry_points))

    def _classify_layers(self, index: CodebaseIndex) -> dict[str, list[str]]:
        """Group files into architecture layers based on directory names."""
        layers: dict[str, list[str]] = {}

        for file_path in index.files:
            parts = file_path.replace("\\", "/").split("/")
            layer = "other"

            for part in parts[:-1]:  # Skip the filename itself
                if part in self._LAYER_PATTERNS:
                    layer = self._LAYER_PATTERNS[part]
                    break

            layers.setdefault(layer, []).append(file_path)

        # Sort files within each layer
        for layer in layers:
            layers[layer] = sorted(layers[layer])

        return layers

    @staticmethod
    def _path_to_module(file_path: str) -> str:
        """Convert a file path to a dotted module name."""
        path = file_path.replace("\\", "/")
        if path.endswith(".py"):
            path = path[:-3]
        elif path.endswith(".js") or path.endswith(".ts"):
            path = path[: path.rfind(".")]
        return path.replace("/", ".")
