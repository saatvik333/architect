"""Scope Governor — evaluates whether a spec stays within MVP boundaries."""

from __future__ import annotations

import json

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from spec_engine.models import ScopeConstraints, ScopeReport, TaskSpec

logger = get_logger(component="spec_engine.scope_governor")

_SYSTEM_PROMPT = """\
You are a scope governance engine for an autonomous coding system. Given a software \
specification and optional constraints, assess the scope of the proposed work.

Evaluate:
1. **Is this MVP-sized?** — Can it be delivered in a single focused iteration?
2. **Deferred features** — Features that are nice-to-have but not essential for the core goal.
3. **Scope creep indicators** — Signs that the spec is trying to do too much at once.
4. **Estimated effort** — Approximate implementation effort in hours.
5. **Recommendations** — Concrete suggestions to tighten scope or improve feasibility.

Respond with ONLY valid JSON in this format:
{
  "is_mvp": true,
  "deferred_features": ["feature that can wait"],
  "scope_creep_flags": ["indicator of scope creep"],
  "estimated_effort_hours": 8.0,
  "recommendations": ["actionable suggestion"]
}
"""


class ScopeGovernor:
    """Evaluates a specification for scope creep and MVP compliance.

    Args:
        llm_client: The LLM client to use for generation.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def evaluate(
        self,
        spec: TaskSpec,
        constraints: ScopeConstraints | None = None,
    ) -> ScopeReport:
        """Evaluate a spec's scope against constraints.

        Args:
            spec: The task specification to evaluate.
            constraints: Optional scope constraints. Defaults to standard limits.

        Returns:
            A :class:`ScopeReport` with scope analysis results.
        """
        if constraints is None:
            constraints = ScopeConstraints()

        spec_text = (
            f"Intent: {spec.intent}\n"
            f"Constraints: {', '.join(spec.constraints) if spec.constraints else 'None'}\n"
            f"Success Criteria ({len(spec.success_criteria)} total):\n"
            + "\n".join(f"  - {c.description}" for c in spec.success_criteria)
            + f"\nFile Targets: {', '.join(spec.file_targets) if spec.file_targets else 'None'}\n"
            f"Assumptions: {', '.join(spec.assumptions) if spec.assumptions else 'None'}\n"
            f"Open Questions: {', '.join(spec.open_questions) if spec.open_questions else 'None'}"
        )

        constraint_text = (
            f"\n\nScope Constraints:\n"
            f"  Max effort hours: {constraints.max_effort_hours}\n"
            f"  Max acceptance criteria: {constraints.max_criteria}\n"
            f"  Enforce MVP: {constraints.enforce_mvp}"
        )

        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Evaluate scope for this specification:\n\n{spec_text}{constraint_text}"
                    ),
                }
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        try:
            response = await self._llm_client.generate(request)
            return self._parse_response(response.content)
        except Exception:
            logger.exception("Scope evaluation failed, returning default report")
            return ScopeReport()

    def _parse_response(self, content: str) -> ScopeReport:
        """Parse the LLM JSON response into a ScopeReport."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Scope governor received invalid JSON from LLM")
            return ScopeReport()

        return ScopeReport(
            is_mvp=data.get("is_mvp", True),
            deferred_features=data.get("deferred_features", []),
            scope_creep_flags=data.get("scope_creep_flags", []),
            estimated_effort_hours=float(data.get("estimated_effort_hours", 0.0)),
            recommendations=data.get("recommendations", []),
        )
