"""Shared pytest fixtures for spec-engine tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse
from spec_engine.models import AcceptanceCriterion, TaskSpec
from spec_engine.parser import SpecParser


def _make_llm_response(content: str) -> LLMResponse:
    """Build a canned LLMResponse with the given text content."""
    return LLMResponse(
        content=content,
        model_id="claude-sonnet-4-20250514",
        input_tokens=200,
        output_tokens=150,
        stop_reason="end_turn",
    )


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Return a mock LLMClient that returns a complete spec JSON."""
    client = AsyncMock(spec=LLMClient)

    spec_json = json.dumps(
        {
            "type": "spec",
            "intent": "Add a greeting function",
            "constraints": ["No external dependencies"],
            "success_criteria": [
                {
                    "description": "Function returns 'Hello, <name>!'",
                    "test_type": "unit",
                    "automated": True,
                }
            ],
            "file_targets": ["src/hello.py", "tests/test_hello.py"],
            "assumptions": ["Python 3.12+"],
            "open_questions": [],
        }
    )

    client.generate.return_value = _make_llm_response(spec_json)
    return client


@pytest.fixture
def ambiguous_llm_client() -> AsyncMock:
    """Return a mock LLMClient that returns clarification questions."""
    client = AsyncMock(spec=LLMClient)

    clarification_json = json.dumps(
        {
            "type": "clarification",
            "questions": [
                {
                    "question": "What programming language should the API use?",
                    "context": "Multiple languages are possible.",
                    "priority": "high",
                },
                {
                    "question": "Should authentication be included?",
                    "context": "The requirement mentions an API but not auth.",
                    "priority": "medium",
                },
            ],
        }
    )

    client.generate.return_value = _make_llm_response(clarification_json)
    return client


@pytest.fixture
def malformed_llm_client() -> AsyncMock:
    """Return a mock LLMClient that returns invalid JSON."""
    client = AsyncMock(spec=LLMClient)
    client.generate.return_value = _make_llm_response("This is not valid JSON at all!")
    return client


@pytest.fixture
def spec_parser(mock_llm_client: AsyncMock) -> SpecParser:
    """Return a SpecParser wired with the default mock LLM client."""
    return SpecParser(mock_llm_client)


@pytest.fixture
def sample_spec() -> TaskSpec:
    """Return a valid sample TaskSpec."""
    return TaskSpec(
        intent="Implement a greeting function",
        constraints=["No external dependencies"],
        success_criteria=[
            AcceptanceCriterion(
                id="ac-test0001",
                description="Function returns greeting string",
                test_type="unit",
            ),
        ],
        file_targets=["src/hello.py"],
        assumptions=["Python 3.12+"],
    )
