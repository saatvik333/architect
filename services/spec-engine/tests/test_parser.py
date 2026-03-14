"""Tests for the SpecParser."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from architect_llm.models import LLMResponse
from spec_engine.models import SpecResult
from spec_engine.parser import SpecParser


class TestSpecParser:
    """Tests for :class:`SpecParser`."""

    async def test_happy_path_returns_spec(
        self,
        spec_parser: SpecParser,
    ) -> None:
        """Parser returns a TaskSpec when LLM produces valid spec JSON."""
        result = await spec_parser.parse("Add a greeting function")

        assert isinstance(result, SpecResult)
        assert result.spec is not None
        assert result.needs_clarification is False
        assert result.spec.intent == "Add a greeting function"
        assert len(result.spec.success_criteria) == 1
        assert result.spec.file_targets == ["src/hello.py", "tests/test_hello.py"]

    async def test_ambiguous_input_returns_questions(
        self,
        ambiguous_llm_client: AsyncMock,
    ) -> None:
        """Parser returns clarification questions when input is ambiguous."""
        parser = SpecParser(ambiguous_llm_client)
        result = await parser.parse("Build me an API")

        assert result.needs_clarification is True
        assert result.spec is None
        assert len(result.questions) == 2
        assert result.questions[0].priority == "high"

    async def test_with_clarifications(
        self,
        mock_llm_client: AsyncMock,
    ) -> None:
        """Parser includes clarification answers in the LLM prompt."""
        parser = SpecParser(mock_llm_client)
        clarifications = {"What language?": "Python", "Framework?": "FastAPI"}

        result = await parser.parse("Build an API", clarifications=clarifications)

        assert result.spec is not None
        # Verify the LLM was called with clarifications in the message
        call_args = mock_llm_client.generate.call_args
        request = call_args[0][0]
        user_msg = request.messages[0]["content"]
        assert "What language?" in user_msg
        assert "Python" in user_msg

    async def test_malformed_llm_response(
        self,
        malformed_llm_client: AsyncMock,
    ) -> None:
        """Parser handles malformed LLM output by requesting clarification."""
        parser = SpecParser(malformed_llm_client)
        result = await parser.parse("Something vague")

        assert result.needs_clarification is True
        assert len(result.questions) == 1
        assert "rephrase" in result.questions[0].question.lower()

    async def test_empty_input(
        self,
        spec_parser: SpecParser,
    ) -> None:
        """Parser returns clarification question for empty input."""
        result = await spec_parser.parse("")

        assert result.needs_clarification is True
        assert len(result.questions) == 1
        assert "empty" in result.questions[0].context.lower()

    async def test_whitespace_only_input(
        self,
        spec_parser: SpecParser,
    ) -> None:
        """Parser treats whitespace-only input as empty."""
        result = await spec_parser.parse("   \n  \t  ")

        assert result.needs_clarification is True
        assert len(result.questions) == 1

    async def test_code_fence_stripping(
        self,
        mock_llm_client: AsyncMock,
    ) -> None:
        """Parser strips markdown code fences from LLM JSON response."""
        spec_json = json.dumps(
            {
                "type": "spec",
                "intent": "Add logging",
                "constraints": [],
                "success_criteria": [
                    {"description": "Logs are written", "test_type": "unit", "automated": True}
                ],
                "file_targets": [],
                "assumptions": [],
                "open_questions": [],
            }
        )
        fenced = f"```json\n{spec_json}\n```"
        mock_llm_client.generate.return_value = LLMResponse(
            content=fenced,
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=100,
            stop_reason="end_turn",
        )

        parser = SpecParser(mock_llm_client)
        result = await parser.parse("Add logging")

        assert result.spec is not None
        assert result.spec.intent == "Add logging"

    async def test_spec_has_default_fields(
        self,
        spec_parser: SpecParser,
    ) -> None:
        """Parsed spec has auto-generated ID and timestamp."""
        result = await spec_parser.parse("Build something")

        assert result.spec is not None
        assert result.spec.id.startswith("spec-")
        assert result.spec.created_at is not None
