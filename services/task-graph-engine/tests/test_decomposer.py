"""Tests for task decomposition."""

from __future__ import annotations

import pytest

from architect_common.enums import AgentType, ModelTier, TaskType
from task_graph_engine.decomposer import TaskDecomposer


@pytest.fixture
def decomposer() -> TaskDecomposer:
    """Return a decomposer without LLM (Phase 1 deterministic mode)."""
    return TaskDecomposer()


@pytest.fixture
def simple_spec() -> dict:
    """A simple spec with two modules."""
    return {
        "name": "test-project",
        "description": "A test project",
        "modules": [
            {
                "name": "auth",
                "description": "Authentication module",
                "priority": 8,
            },
            {
                "name": "api",
                "description": "API layer",
                "priority": 5,
            },
        ],
    }


@pytest.fixture
def single_module_spec() -> dict:
    """A spec with a single module."""
    return {
        "name": "simple-service",
        "description": "A simple service",
        "modules": [
            {
                "name": "core",
                "description": "Core logic",
                "priority": 5,
                "model_tier": "tier_1",
            },
        ],
    }


@pytest.fixture
def empty_spec() -> dict:
    """A spec with no modules — should produce one default triplet."""
    return {
        "name": "bare-project",
        "description": "No modules specified",
    }


class TestDeterministicDecomposition:
    """Tests for the Phase 1 deterministic decomposer."""

    async def test_produces_three_tasks_per_module(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)
        # 2 modules x 3 tasks (impl + test + review) = 6 tasks.
        assert len(tasks) == 6

    async def test_single_module_produces_triplet(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        assert len(tasks) == 3

    async def test_empty_spec_produces_default_triplet(self, decomposer, empty_spec):
        tasks = await decomposer.decompose_spec(empty_spec)
        assert len(tasks) == 3

    async def test_task_types_in_triplet(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        types = [t.type for t in tasks]
        assert TaskType.IMPLEMENT_FEATURE in types
        assert TaskType.WRITE_TEST in types
        assert TaskType.REVIEW_CODE in types

    async def test_agent_types_in_triplet(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        agent_types = {t.agent_type for t in tasks}
        assert AgentType.CODER in agent_types
        assert AgentType.TESTER in agent_types
        assert AgentType.REVIEWER in agent_types

    async def test_model_tier_from_spec(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        assert impl_task.model_tier == ModelTier.TIER_1

    async def test_review_has_higher_priority(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        review_task = next(t for t in tasks if t.type == TaskType.REVIEW_CODE)
        assert review_task.priority > impl_task.priority


class TestTaskDependencies:
    """Tests that dependencies are wired correctly in the decomposed output."""

    async def test_test_depends_on_implementation(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        test_task = next(t for t in tasks if t.type == TaskType.WRITE_TEST)
        assert impl_task.id in test_task.dependencies

    async def test_review_depends_on_impl_and_test(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        test_task = next(t for t in tasks if t.type == TaskType.WRITE_TEST)
        review_task = next(t for t in tasks if t.type == TaskType.REVIEW_CODE)
        assert impl_task.id in review_task.dependencies
        assert test_task.id in review_task.dependencies

    async def test_implementation_has_no_deps(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        assert impl_task.dependencies == []

    async def test_all_task_ids_unique(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)
        ids = [t.id for t in tasks]
        assert len(set(ids)) == len(ids)


class TestTaskProperties:
    """Tests for properties of generated tasks."""

    async def test_tasks_have_descriptions(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)
        for task in tasks:
            assert task.description, f"Task {task.id} has empty description"

    async def test_tasks_have_budgets(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        for task in tasks:
            assert task.budget.max_tokens > 0
            assert task.budget.max_retries >= 0

    async def test_implementation_task_has_spec_input(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        input_keys = [inp.key for inp in impl_task.inputs]
        assert "spec" in input_keys

    async def test_test_task_has_implementation_input(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        test_task = next(t for t in tasks if t.type == TaskType.WRITE_TEST)
        input_keys = [inp.key for inp in test_task.inputs]
        assert "implementation" in input_keys

    async def test_review_task_has_both_inputs(self, decomposer, single_module_spec):
        tasks = await decomposer.decompose_spec(single_module_spec)
        review_task = next(t for t in tasks if t.type == TaskType.REVIEW_CODE)
        input_keys = [inp.key for inp in review_task.inputs]
        assert "implementation" in input_keys
        assert "tests" in input_keys

    async def test_all_tasks_start_pending(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)
        from architect_common.enums import StatusEnum

        for task in tasks:
            assert task.status == StatusEnum.PENDING

    async def test_custom_max_tokens(self, decomposer):
        spec = {
            "modules": [
                {"name": "big-module", "max_tokens": 200_000, "priority": 5},
            ],
        }
        tasks = await decomposer.decompose_spec(spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        assert impl_task.budget.max_tokens == 200_000

    async def test_custom_max_retries(self, decomposer):
        spec = {
            "modules": [
                {"name": "fragile", "max_retries": 5, "priority": 3},
            ],
        }
        tasks = await decomposer.decompose_spec(spec)
        impl_task = next(t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE)
        assert impl_task.budget.max_retries == 5


class TestMultiModuleDecomposition:
    """Tests for specs with multiple modules."""

    async def test_modules_produce_independent_triplets(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)

        # Group by module: each impl task's deps should not cross modules.
        impl_tasks = [t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE]
        assert len(impl_tasks) == 2

        for impl in impl_tasks:
            assert impl.dependencies == []

    async def test_preserves_priority_from_spec(self, decomposer, simple_spec):
        tasks = await decomposer.decompose_spec(simple_spec)

        impl_tasks = [t for t in tasks if t.type == TaskType.IMPLEMENT_FEATURE]
        priorities = sorted([t.priority for t in impl_tasks], reverse=True)
        assert priorities[0] == 8  # auth module
        assert priorities[1] == 5  # api module
