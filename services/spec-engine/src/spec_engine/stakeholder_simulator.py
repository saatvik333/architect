"""Stakeholder Simulator — role-plays multiple personas to review a TaskSpec."""

from __future__ import annotations

import json

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from spec_engine.models import StakeholderConcern, StakeholderReview, TaskSpec

logger = get_logger(component="spec_engine.stakeholder_simulator")

_SYSTEM_PROMPT = """\
You are a stakeholder simulation engine. Given a software specification, you must \
role-play exactly 4 personas and review the spec from each perspective:

1. **End User** — focuses on usability, clarity, and whether the feature meets real needs.
2. **Security Reviewer** — focuses on attack surface, data exposure, auth, and trust boundaries.
3. **Product Manager** — focuses on business value, prioritisation, and alignment with goals.
4. **Ops Engineer** — focuses on deployability, observability, performance, and failure modes.

For each persona, raise zero or more concerns. Each concern has:
- ``role``: one of "end_user", "security_reviewer", "product_manager", "ops_engineer"
- ``concern``: a concise description of the issue
- ``severity``: "low", "medium", or "high"
- ``suggestion``: a concrete recommendation to address the concern

After listing all concerns, provide:
- ``overall_risk``: "low", "medium", or "high" (the highest severity among all concerns, \
or "low" if there are none)
- ``summary``: a 1-2 sentence overall assessment

Respond with ONLY valid JSON in this format:
{
  "concerns": [
    {"role": "...", "concern": "...", "severity": "low|medium|high", "suggestion": "..."}
  ],
  "overall_risk": "low|medium|high",
  "summary": "..."
}
"""


class StakeholderSimulator:
    """Simulates multiple stakeholder personas reviewing a specification.

    Args:
        llm_client: The LLM client to use for generation.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def simulate(self, spec: TaskSpec) -> StakeholderReview:
        """Run stakeholder simulation on a spec.

        Args:
            spec: The task specification to review.

        Returns:
            A :class:`StakeholderReview` with concerns from all personas.
        """
        spec_text = (
            f"Intent: {spec.intent}\n"
            f"Constraints: {', '.join(spec.constraints) if spec.constraints else 'None'}\n"
            f"Success Criteria:\n"
            + "\n".join(f"  - {c.description}" for c in spec.success_criteria)
            + f"\nFile Targets: {', '.join(spec.file_targets) if spec.file_targets else 'None'}\n"
            f"Assumptions: {', '.join(spec.assumptions) if spec.assumptions else 'None'}\n"
            f"Open Questions: {', '.join(spec.open_questions) if spec.open_questions else 'None'}"
        )

        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Review this specification:\n\n{spec_text}"}],
            max_tokens=4096,
            temperature=0.3,
        )

        try:
            response = await self._llm_client.generate(request)
            return self._parse_response(response.content)
        except Exception:
            logger.exception("Stakeholder simulation failed, returning empty review")
            return StakeholderReview()

    def _parse_response(self, content: str) -> StakeholderReview:
        """Parse the LLM JSON response into a StakeholderReview."""
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
            logger.warning("Stakeholder simulator received invalid JSON from LLM")
            return StakeholderReview()

        concerns = [
            StakeholderConcern(
                role=c.get("role", "unknown"),
                concern=c.get("concern", ""),
                severity=c.get("severity", "low"),
                suggestion=c.get("suggestion", ""),
            )
            for c in data.get("concerns", [])
        ]

        return StakeholderReview(
            concerns=concerns,
            overall_risk=data.get("overall_risk", "low"),
            summary=data.get("summary", ""),
        )
