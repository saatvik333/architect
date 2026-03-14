"""Spec parser — transforms raw natural-language text into a TaskSpec via LLM."""

from __future__ import annotations

import json
import logging

from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from spec_engine.models import (
    AcceptanceCriterion,
    ClarificationQuestion,
    SpecResult,
    TaskSpec,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a specification engine for the ARCHITECT autonomous coding system.
Your job is to transform vague human intent into a precise, testable specification.

Given raw text describing what the user wants, extract:
1. **intent** — a clear one-sentence summary of the goal
2. **constraints** — any limitations or requirements mentioned
3. **success_criteria** — concrete, testable acceptance criteria
4. **file_targets** — files likely to be created or modified
5. **assumptions** — assumptions you are making
6. **open_questions** — anything ambiguous that needs clarification

If the input is too ambiguous to produce a useful spec, return clarification questions instead.

Respond with ONLY valid JSON in one of these two formats:

Format A (complete spec):
{
  "type": "spec",
  "intent": "...",
  "constraints": ["..."],
  "success_criteria": [
    {"description": "...", "test_type": "unit|integration|adversarial", "automated": true}
  ],
  "file_targets": ["..."],
  "assumptions": ["..."],
  "open_questions": ["..."]
}

Format B (needs clarification):
{
  "type": "clarification",
  "questions": [
    {"question": "...", "context": "...", "priority": "high|medium|low"}
  ]
}
"""


class SpecParser:
    """Parses raw natural-language text into a structured TaskSpec using an LLM.

    Args:
        llm_client: The LLM client to use for generation.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def parse(
        self,
        raw_text: str,
        clarifications: dict[str, str] | None = None,
    ) -> SpecResult:
        """Parse raw text into a SpecResult.

        Args:
            raw_text: The natural-language description of what to build.
            clarifications: Optional dict of question→answer pairs from
                a prior clarification round.

        Returns:
            A :class:`SpecResult` containing either a complete spec or
            clarification questions.
        """
        if not raw_text.strip():
            return SpecResult(
                needs_clarification=True,
                questions=[
                    ClarificationQuestion(
                        question="What would you like to build?",
                        context="The input was empty.",
                        priority="high",
                    )
                ],
            )

        user_content = f"Raw requirement:\n{raw_text}"
        if clarifications:
            qa_block = "\n".join(f"Q: {q}\nA: {a}" for q, a in clarifications.items())
            user_content += f"\n\nPrevious clarifications:\n{qa_block}"

        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=4096,
            temperature=0.1,
        )

        response = await self._llm_client.generate(request)
        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> SpecResult:
        """Parse the LLM JSON response into a SpecResult."""
        # Strip markdown code fences if present
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (code fences)
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON, requesting clarification")
            return SpecResult(
                needs_clarification=True,
                questions=[
                    ClarificationQuestion(
                        question="Could you rephrase your requirement more clearly?",
                        context="The system could not parse the requirement into a specification.",
                        priority="high",
                    )
                ],
            )

        if data.get("type") == "clarification":
            questions = [
                ClarificationQuestion(
                    question=q["question"],
                    context=q.get("context", ""),
                    priority=q.get("priority", "medium"),
                )
                for q in data.get("questions", [])
            ]
            return SpecResult(needs_clarification=True, questions=questions)

        # Build a TaskSpec from the structured response
        criteria = [
            AcceptanceCriterion(
                description=c["description"],
                test_type=c.get("test_type", "unit"),
                automated=c.get("automated", True),
            )
            for c in data.get("success_criteria", [])
        ]

        spec = TaskSpec(
            intent=data.get("intent", ""),
            constraints=data.get("constraints", []),
            success_criteria=criteria,
            file_targets=data.get("file_targets", []),
            assumptions=data.get("assumptions", []),
            open_questions=data.get("open_questions", []),
        )

        return SpecResult(spec=spec)
