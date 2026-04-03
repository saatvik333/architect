"""Heuristic rule matching and evolution.

Heuristics live at L3 (heuristic layer) and provide concrete
condition-action rules that agents can apply during task execution.
"""

from __future__ import annotations

import json
from typing import Any

from architect_common.logging import get_logger
from architect_common.types import HeuristicId, new_heuristic_id
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.llm_utils import parse_llm_json_array
from knowledge_memory.models import HeuristicRule

logger = get_logger(component="knowledge_memory.heuristic_engine")

_STOP_WORDS = frozenset(
    {
        "when",
        "then",
        "with",
        "that",
        "this",
        "from",
        "have",
        "been",
        "will",
        "each",
        "into",
        "also",
    }
)


class HeuristicEngine:
    """Matches, evolves, and synthesizes heuristic rules."""

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._store = knowledge_store
        self._llm = llm_client

    async def match_heuristics(
        self,
        *,
        task_type: str | None = None,
        domain: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[HeuristicRule]:
        """Find heuristics matching the given task type and domain.

        Returns active heuristics ordered by confidence (descending).
        Optional context dict is used for basic keyword matching against
        the heuristic condition text.
        """
        raw_heuristics = await self._store.get_active_heuristics(domain=domain)

        results: list[HeuristicRule] = []
        for h in raw_heuristics:
            # Basic keyword matching against condition
            condition = h.get("condition", "")
            matches_task = task_type is None or task_type in condition
            matches_domain = domain is None or domain in condition
            if not matches_task and not matches_domain:
                continue

            source_ids = h.get("source_pattern_ids", [])
            if isinstance(source_ids, str):
                source_ids = json.loads(source_ids)

            results.append(
                HeuristicRule(
                    id=HeuristicId(h["id"]),
                    domain=h.get("domain", ""),
                    condition=h.get("condition", ""),
                    action=h.get("action", ""),
                    rationale=h.get("rationale", ""),
                    confidence=float(h.get("confidence", 0.5)),
                    success_count=int(h.get("success_count", 0)),
                    failure_count=int(h.get("failure_count", 0)),
                    active=bool(h.get("active", True)),
                    source_pattern_ids=source_ids,
                )
            )

        # Filter by context keywords if provided
        if context:
            context_str = " ".join(str(v) for v in context.values()).lower()
            results = [
                r
                for r in results
                if any(
                    word in context_str
                    for word in r.condition.lower().split()
                    if len(word) > 4 and word not in _STOP_WORDS
                )
                or not context_str  # include all if context is effectively empty
            ]

        return results

    async def evolve_heuristic(
        self,
        heuristic_id: HeuristicId,
        *,
        success: bool,
    ) -> None:
        """Record an outcome for a heuristic and update its confidence."""
        await self._store.update_heuristic_outcome(heuristic_id, success=success)
        logger.info(
            "evolved heuristic",
            heuristic_id=str(heuristic_id),
            success=success,
        )

    async def synthesize_heuristics(
        self,
        patterns: list[dict[str, Any]],
    ) -> list[HeuristicRule]:
        """Use an LLM to synthesize heuristic rules from extracted patterns.

        Patterns are L2 entries.  The LLM generates condition-action rules
        that represent actionable advice for agents.
        """
        if not patterns or self._llm is None:
            return []

        pattern_summaries = []
        for p in patterns:
            pattern_summaries.append(
                f"- {p.get('title', 'Untitled')}: {p.get('content', '')[:200]}"
            )

        pattern_text = "\n".join(pattern_summaries)
        domain = patterns[0].get("topic", "general") if patterns else "general"

        request = LLMRequest(
            system_prompt=(
                "You are an expert software engineering heuristic synthesizer. "
                "Given a set of patterns extracted from task observations, "
                "synthesize actionable heuristic rules. "
                "Return a JSON array of rule objects with keys: "
                '"domain", "condition" (when to apply), "action" (what to do), '
                '"rationale" (why this works), "confidence" (0-1 float).'
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Domain: <user_input>{domain}</user_input>\n\n"
                        f"Patterns ({len(patterns)} total):\n<user_input>{pattern_text}</user_input>\n\n"
                        "Synthesize heuristic rules from these patterns. "
                        "Return ONLY a JSON array."
                    ),
                }
            ],
            max_tokens=4000,
            temperature=0.3,
        )

        response = await self._llm.generate(request)

        rules: list[HeuristicRule] = []
        for rr in parse_llm_json_array(response.content, logger):
            rule = HeuristicRule(
                id=new_heuristic_id(),
                domain=rr.get("domain", domain),
                condition=rr.get("condition", ""),
                action=rr.get("action", ""),
                rationale=rr.get("rationale", ""),
                confidence=float(rr.get("confidence", 0.5)),
            )
            rules.append(rule)

        logger.info("synthesized heuristics", count=len(rules), domain=domain)
        return rules
