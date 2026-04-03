"""Post-mortem analysis engine using LLM to generate actionable improvements."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from architect_common.enums import FailureCode
from architect_common.logging import get_logger
from architect_common.types import new_post_mortem_id
from architect_db.models.failure import FailureRecord
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest

from .models import (
    AdversarialTest,
    HeuristicUpdate,
    PostMortemAnalysis,
    PromptImprovement,
    TopologyRecommendation,
)

logger = get_logger(component="failure_taxonomy.post_mortem_analyzer")


class PostMortemAnalyzer:
    """Generates post-mortem analysis and improvement proposals from failure records.

    Uses the LLM to analyze patterns across failures and produce actionable
    improvements: prompt changes, adversarial tests, heuristic updates, and
    topology recommendations.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    async def analyze(
        self,
        project_id: str,
        failure_records: list[FailureRecord],
    ) -> PostMortemAnalysis:
        """Run post-mortem analysis on a collection of failure records.

        Args:
            project_id: The project these failures belong to.
            failure_records: The failure records to analyze.

        Returns:
            A :class:`PostMortemAnalysis` with grouped findings and improvements.
        """
        post_mortem_id = new_post_mortem_id()

        # Build failure summary (count by code)
        code_counter: Counter[str] = Counter()
        for record in failure_records:
            code_counter[record.failure_code] += 1
        failure_summary = dict(code_counter)

        # Extract root causes from records
        root_causes = [record.root_cause for record in failure_records if record.root_cause]

        # If we have an LLM client, use it to generate improvements
        if self._llm_client is not None:
            try:
                improvements = await self._generate_improvements(
                    project_id, failure_records, failure_summary
                )
                return PostMortemAnalysis(
                    post_mortem_id=post_mortem_id,
                    project_id=project_id,
                    failure_summary=failure_summary,
                    root_causes=root_causes,
                    **improvements,
                )
            except Exception:
                logger.warning(
                    "llm-based post-mortem failed, returning basic analysis",
                    project_id=project_id,
                    exc_info=True,
                )

        # Fallback: basic analysis without LLM
        return PostMortemAnalysis(
            post_mortem_id=post_mortem_id,
            project_id=project_id,
            failure_summary=failure_summary,
            root_causes=root_causes,
        )

    async def _generate_improvements(
        self,
        project_id: str,
        failure_records: list[FailureRecord],
        failure_summary: dict[str, int],
    ) -> dict[str, Any]:
        """Use the LLM to generate improvement proposals."""
        assert self._llm_client is not None

        failures_text = "\n".join(
            f"- [{r.failure_code}] {r.summary} (severity={r.severity})"
            for r in failure_records[:50]  # cap to avoid token overflow
        )

        summary_text = ", ".join(f"{k}: {v}" for k, v in failure_summary.items())

        system_prompt = (
            "You are a post-mortem analysis expert for the ARCHITECT autonomous coding system. "
            "Given a set of classified failures, generate actionable improvements.\n\n"
            "Respond with valid JSON only, no markdown fences:\n"
            "{\n"
            '  "prompt_improvements": [{"target_agent_type": "<type>", "current_prompt_excerpt": "", '
            '"suggested_change": "<change>", "rationale": "<why>"}],\n'
            '  "adversarial_tests": [{"test_name": "<name>", "test_description": "<desc>", '
            '"attack_vector": "<vector>", "expected_behavior": "<behavior>"}],\n'
            '  "heuristic_updates": [{"domain": "<domain>", "condition": "<if>", '
            '"action": "<then>", "source_failure_codes": ["<code>"]}],\n'
            '  "topology_recommendations": [{"recommendation": "<what>", '
            '"rationale": "<why>", "estimated_impact": "<impact>"}]\n'
            "}"
        )

        user_content = (
            f"Project: {project_id}\n"
            f"Failure summary: {summary_text}\n\n"
            f"Failures:\n<user_input>{failures_text}</user_input>"
        )

        llm_request = LLMRequest(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=4000,
            temperature=0.3,
        )

        response = await self._llm_client.generate(llm_request)
        return self._parse_improvements(response.content)

    def _parse_improvements(self, content: str) -> dict[str, Any]:
        """Parse LLM response into typed improvement objects."""
        try:
            data: dict[str, Any] = json.loads(content.strip())
        except json.JSONDecodeError:
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                raise

        result: dict[str, Any] = {}

        # Parse prompt improvements
        raw_prompts = data.get("prompt_improvements", [])
        result["prompt_improvements"] = [
            PromptImprovement(
                target_agent_type=p.get("target_agent_type", "coder"),
                current_prompt_excerpt=p.get("current_prompt_excerpt", ""),
                suggested_change=p.get("suggested_change", ""),
                rationale=p.get("rationale", ""),
            )
            for p in raw_prompts
            if isinstance(p, dict)
        ]

        # Parse adversarial tests
        raw_tests = data.get("adversarial_tests", [])
        result["adversarial_tests"] = [
            AdversarialTest(
                test_name=t.get("test_name", ""),
                test_description=t.get("test_description", ""),
                attack_vector=t.get("attack_vector", ""),
                expected_behavior=t.get("expected_behavior", ""),
            )
            for t in raw_tests
            if isinstance(t, dict)
        ]

        # Parse heuristic updates
        raw_heuristics = data.get("heuristic_updates", [])
        result["heuristic_updates"] = [
            HeuristicUpdate(
                domain=h.get("domain", ""),
                condition=h.get("condition", ""),
                action=h.get("action", ""),
                source_failure_codes=[
                    FailureCode(c)
                    for c in h.get("source_failure_codes", [])
                    if c in [fc.value for fc in FailureCode]
                ],
            )
            for h in raw_heuristics
            if isinstance(h, dict)
        ]

        # Parse topology recommendations
        raw_topology = data.get("topology_recommendations", [])
        result["topology_recommendations"] = [
            TopologyRecommendation(
                recommendation=tr.get("recommendation", ""),
                rationale=tr.get("rationale", ""),
                estimated_impact=tr.get("estimated_impact", ""),
            )
            for tr in raw_topology
            if isinstance(tr, dict)
        ]

        return result
