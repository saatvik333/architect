"""Tests for the ArchitectureMapGenerator."""

from __future__ import annotations

import pytest

from codebase_comprehension.architecture_map import ArchitectureMapGenerator
from codebase_comprehension.models import (
    CodebaseIndex,
    FileIndex,
    FunctionDef,
    ImportInfo,
)


@pytest.fixture
def generator() -> ArchitectureMapGenerator:
    """Return a fresh ArchitectureMapGenerator."""
    return ArchitectureMapGenerator()


@pytest.fixture
def sample_index() -> CodebaseIndex:
    """Return a CodebaseIndex with a realistic directory structure."""
    files: dict[str, FileIndex] = {
        "src/api/routes.py": FileIndex(
            path="src/api/routes.py",
            functions=[
                FunctionDef(
                    name="get_items",
                    file_path="src/api/routes.py",
                    line_number=5,
                ),
            ],
            imports=[
                ImportInfo(module="fastapi", names=["APIRouter"]),
                ImportInfo(module="src.services.item_service", names=["ItemService"]),
            ],
        ),
        "src/models/item.py": FileIndex(
            path="src/models/item.py",
            imports=[
                ImportInfo(module="pydantic", names=["BaseModel"]),
            ],
        ),
        "src/services/item_service.py": FileIndex(
            path="src/services/item_service.py",
            functions=[
                FunctionDef(
                    name="create_app",
                    file_path="src/services/item_service.py",
                    line_number=10,
                ),
            ],
            imports=[
                ImportInfo(module="src.models.item", names=["Item"]),
            ],
        ),
        "src/utils/helpers.py": FileIndex(
            path="src/utils/helpers.py",
            functions=[
                FunctionDef(
                    name="format_name",
                    file_path="src/utils/helpers.py",
                    line_number=1,
                ),
            ],
        ),
        "tests/test_routes.py": FileIndex(
            path="tests/test_routes.py",
            functions=[
                FunctionDef(
                    name="test_get_items",
                    file_path="tests/test_routes.py",
                    line_number=1,
                ),
            ],
            imports=[
                ImportInfo(module="pytest", names=["pytest"]),
            ],
        ),
        "src/main.py": FileIndex(
            path="src/main.py",
            functions=[
                FunctionDef(
                    name="main",
                    file_path="src/main.py",
                    line_number=1,
                ),
            ],
        ),
    }

    return CodebaseIndex(
        root_path="/project",
        files=files,
        total_files=len(files),
        total_symbols=6,
    )


class TestModuleDependencies:
    """Test module dependency graph generation."""

    def test_modules_populated(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        assert len(arch_map.modules) > 0
        # routes module should depend on fastapi and item_service
        routes_key = "src.api.routes"
        assert routes_key in arch_map.modules
        assert "fastapi" in arch_map.modules[routes_key]

    def test_module_with_no_imports(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        helpers_key = "src.utils.helpers"
        assert helpers_key in arch_map.modules
        assert arch_map.modules[helpers_key] == []


class TestEntryPoints:
    """Test entry point detection."""

    def test_main_detected(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        assert "src/main.py" in arch_map.entry_points

    def test_create_app_detected(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        # item_service.py has a create_app function
        assert "src/services/item_service.py" in arch_map.entry_points


class TestLayerClassification:
    """Test file-to-layer classification."""

    def test_layers_populated(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        assert "api" in arch_map.layers
        assert "models" in arch_map.layers
        assert "services" in arch_map.layers
        assert "utils" in arch_map.layers
        assert "tests" in arch_map.layers

    def test_routes_in_api_layer(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        assert "src/api/routes.py" in arch_map.layers["api"]

    def test_test_files_in_tests_layer(
        self, generator: ArchitectureMapGenerator, sample_index: CodebaseIndex
    ) -> None:
        arch_map = generator.generate(sample_index)

        assert "tests/test_routes.py" in arch_map.layers["tests"]


class TestEmptyIndex:
    """Test with an empty codebase index."""

    def test_empty_index_produces_empty_map(self, generator: ArchitectureMapGenerator) -> None:
        empty = CodebaseIndex(root_path="/empty", files={})
        arch_map = generator.generate(empty)

        assert arch_map.modules == {}
        assert arch_map.entry_points == []
        assert arch_map.layers == {}
