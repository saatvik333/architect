"""Task decomposition: converts a specification into a list of tasks."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from architect_common.enums import AgentType, ModelTier, TaskType
from architect_common.logging import get_logger
from architect_common.types import new_task_id
from task_graph_engine.models import Task, TaskBudget, TaskInput

if TYPE_CHECKING:
    from architect_llm.client import LLMClient

logger = get_logger(component="task_decomposer")


class TaskDecomposer:
    """Breaks a high-level specification into executable tasks.

    Phase 1 uses a simple deterministic decomposition strategy: for each
    module in the spec, create an implementation task, a test task (depends
    on the implementation), and a review task (depends on both).

    When an :class:`LLMClient` is provided, future phases will use
    intelligent decomposition that reasons about dependencies and task
    boundaries.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    async def decompose_spec(self, spec: dict[str, Any]) -> list[Task]:
        """Decompose a project specification into a list of tasks.

        The spec is expected to contain a ``"modules"`` key with a list of
        module descriptors.  Each module produces an implementation + test +
        review triplet.

        If an LLM client is available and the spec contains ``"use_llm": True``,
        the decomposition is delegated to the LLM for a richer task graph.

        Args:
            spec: A project specification dictionary.

        Returns:
            A flat list of :class:`Task` instances with dependency IDs set.
        """
        if self._llm_client and spec.get("use_llm", False):
            return await self._llm_decompose(spec)

        return self._deterministic_decompose(spec)

    # ── Deterministic (Phase 1) ─────────────────────────────────────

    def _deterministic_decompose(self, spec: dict[str, Any]) -> list[Task]:
        """Create a simple impl -> test -> review chain per module."""
        modules: list[dict[str, Any]] = spec.get("modules", [])
        if not modules:
            # If no modules, treat the whole spec as a single module.
            modules = [
                {"name": spec.get("name", "main"), "description": spec.get("description", "")}
            ]

        all_tasks: list[Task] = []
        for module in modules:
            impl = self._create_implementation_task(module)
            test = self._create_test_task(impl)
            review = self._create_review_task(impl, test)
            all_tasks.extend([impl, test, review])

        logger.info(
            "Decomposed spec into tasks",
            task_count=len(all_tasks),
            module_count=len(modules),
        )
        return all_tasks

    def _create_implementation_task(self, module: dict[str, Any]) -> Task:
        """Create an implementation task for a single module."""
        name = module.get("name", "unnamed")
        description = module.get("description", "")
        priority = module.get("priority", 5)
        model_tier = ModelTier(module.get("model_tier", ModelTier.TIER_2))

        return Task(
            id=new_task_id(),
            type=TaskType.IMPLEMENT_FEATURE,
            agent_type=AgentType.CODER,
            model_tier=model_tier,
            priority=priority,
            description=f"Implement module: {name}. {description}".strip(),
            inputs=[
                TaskInput(key="spec", artifact_uri="", content_hash=""),
            ],
            budget=TaskBudget(
                max_tokens=module.get("max_tokens", 100_000),
                max_retries=module.get("max_retries", 3),
            ),
        )

    def _create_test_task(self, impl_task: Task) -> Task:
        """Create a test-writing task that depends on an implementation task."""
        return Task(
            id=new_task_id(),
            type=TaskType.WRITE_TEST,
            agent_type=AgentType.TESTER,
            model_tier=ModelTier.TIER_2,
            priority=impl_task.priority,
            description=f"Write tests for: {impl_task.description}",
            dependencies=[impl_task.id],
            inputs=[
                TaskInput(key="implementation", artifact_uri="", content_hash=""),
            ],
            budget=TaskBudget(
                max_tokens=50_000,
                max_retries=2,
            ),
        )

    def _create_review_task(self, impl_task: Task, test_task: Task) -> Task:
        """Create a review task that depends on both implementation and testing."""
        return Task(
            id=new_task_id(),
            type=TaskType.REVIEW_CODE,
            agent_type=AgentType.REVIEWER,
            model_tier=ModelTier.TIER_1,
            priority=impl_task.priority + 1,  # Reviews are slightly higher priority.
            description=f"Review: {impl_task.description}",
            dependencies=[impl_task.id, test_task.id],
            inputs=[
                TaskInput(key="implementation", artifact_uri="", content_hash=""),
                TaskInput(key="tests", artifact_uri="", content_hash=""),
            ],
            budget=TaskBudget(
                max_tokens=30_000,
                max_retries=1,
            ),
        )

    # ── LLM-assisted decomposition (Phase 2+) ─────────────────────

    async def _llm_decompose(self, spec: dict[str, Any]) -> list[Task]:
        """Use the LLM to produce a richer decomposition.

        The LLM receives the full spec and returns a JSON array of task
        descriptors.  Each descriptor is validated and converted to a
        :class:`Task`.
        """
        assert self._llm_client is not None

        from architect_llm.models import LLMRequest

        request = LLMRequest(
            system_prompt=(
                "You are an expert software architect. Decompose the following "
                "specification into a list of tasks. Each task should have:\n"
                '- "name": short name\n'
                '- "type": one of implement_feature, write_test, review_code, fix_bug, refactor\n'
                '- "agent_type": one of coder, reviewer, tester, planner\n'
                '- "model_tier": one of tier_1, tier_2, tier_3\n'
                '- "priority": integer 0-10\n'
                '- "description": what the task does\n'
                '- "dependencies": list of task names this depends on\n'
                "\nReturn ONLY a JSON array, no markdown fences."
            ),
            messages=[{"role": "user", "content": json.dumps(spec)}],
            max_tokens=8_000,
            temperature=0.3,
        )

        response = await self._llm_client.generate(request)

        # Strip markdown code fences that LLMs sometimes add despite instructions.
        content = response.content.strip()
        content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
        content = re.sub(r"\n?```\s*$", "", content.strip())

        try:
            raw_tasks: list[dict[str, Any]] = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON for task decomposition: {exc}") from exc

        # Map task names to IDs for dependency resolution.
        name_to_id: dict[str, str] = {}
        tasks: list[Task] = []

        for raw in raw_tasks:
            task_id = new_task_id()
            name_to_id[raw["name"]] = task_id

        for raw in raw_tasks:
            task_id_str = name_to_id[raw["name"]]
            dep_ids = [
                name_to_id[dep_name]
                for dep_name in raw.get("dependencies", [])
                if dep_name in name_to_id
            ]
            task = Task(
                id=task_id_str,
                type=TaskType(raw.get("type", "implement_feature")),
                agent_type=AgentType(raw.get("agent_type", "coder")),
                model_tier=ModelTier(raw.get("model_tier", "tier_2")),
                priority=raw.get("priority", 5),
                description=raw.get("description", raw["name"]),
                dependencies=dep_ids,
            )
            tasks.append(task)

        logger.info(
            "LLM decomposed spec into tasks",
            task_count=len(tasks),
        )
        return tasks
