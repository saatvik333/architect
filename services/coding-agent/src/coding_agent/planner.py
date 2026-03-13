"""Task planner: generates an implementation plan via LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.logging import get_logger
from architect_llm.models import LLMRequest
from coding_agent.models import CodebaseContext, SpecContext

if TYPE_CHECKING:
    from architect_llm.client import LLMClient

logger = get_logger(component="coding_agent.planner")


class TaskPlanner:
    """Generates a structured implementation plan via the LLM.

    The plan is a markdown string describing the approach, file changes,
    and testing strategy the agent should follow.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def plan(
        self,
        spec: SpecContext,
        codebase: CodebaseContext,
    ) -> str:
        """Generate an implementation plan.

        Args:
            spec: The task specification.
            codebase: Snapshot of the relevant codebase.

        Returns:
            A markdown implementation plan string.
        """
        system_prompt = (
            "You are a senior software architect. Given a task specification and "
            "codebase context, produce a concise implementation plan.\n"
            "\n"
            "The plan MUST include:\n"
            "1. Files to create or modify (with paths)\n"
            "2. Key design decisions and rationale\n"
            "3. Testing strategy\n"
            "4. Potential risks or edge cases\n"
            "\n"
            "Output ONLY the plan as markdown, no preamble."
        )

        user_content = self._build_planning_prompt(spec, codebase)

        request = LLMRequest(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=4_000,
            temperature=0.3,
        )

        logger.info(
            "generating implementation plan",
            task_title=spec.title,
        )

        response = await self._llm.generate(request)

        logger.info(
            "plan generated",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        return response.content

    @staticmethod
    def _build_planning_prompt(spec: SpecContext, codebase: CodebaseContext) -> str:
        """Assemble the user prompt for the planning request."""
        parts: list[str] = []

        parts.append(f"## Task: {spec.title}")
        if spec.description:
            parts.append(spec.description)
        if spec.acceptance_criteria:
            parts.append("\n### Acceptance Criteria")
            for ac in spec.acceptance_criteria:
                parts.append(f"- {ac}")
        if spec.constraints:
            parts.append("\n### Constraints")
            for c in spec.constraints:
                parts.append(f"- {c}")

        if codebase.relevant_files:
            parts.append("\n### Relevant Files")
            for f in codebase.relevant_files:
                parts.append(f"- `{f}`")

        if codebase.file_contents:
            parts.append("\n### File Contents")
            for path, content in codebase.file_contents.items():
                parts.append(f"\n#### {path}\n```python\n{content}\n```")

        return "\n".join(parts)
