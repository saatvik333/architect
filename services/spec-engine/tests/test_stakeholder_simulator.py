"""Tests for the StakeholderSimulator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse
from spec_engine.models import AcceptanceCriterion, StakeholderReview, TaskSpec
from spec_engine.stakeholder_simulator import StakeholderSimulator


def _make_llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model_id="claude-sonnet-4-20250514",
        input_tokens=200,
        output_tokens=150,
        stop_reason="end_turn",
    )


@pytest.fixture
def sample_spec() -> TaskSpec:
    return TaskSpec(
        intent="Implement a REST API for user management",
        constraints=["Must use FastAPI", "No external auth providers"],
        success_criteria=[
            AcceptanceCriterion(
                id="ac-test0001",
                description="CRUD endpoints for users work correctly",
                test_type="integration",
            ),
        ],
        file_targets=["src/api/users.py"],
        assumptions=["Python 3.12+"],
    )


@pytest.fixture
def review_response_json() -> str:
    return json.dumps(
        {
            "concerns": [
                {
                    "role": "end_user",
                    "concern": "No mention of input validation for user fields",
                    "severity": "medium",
                    "suggestion": "Add explicit validation rules for email and name fields",
                },
                {
                    "role": "security_reviewer",
                    "concern": "No authentication mechanism specified",
                    "severity": "high",
                    "suggestion": "Add JWT or API key authentication before deployment",
                },
                {
                    "role": "product_manager",
                    "concern": "No pagination for listing users",
                    "severity": "low",
                    "suggestion": "Add offset/limit parameters to the list endpoint",
                },
                {
                    "role": "ops_engineer",
                    "concern": "No health check or observability endpoints mentioned",
                    "severity": "medium",
                    "suggestion": "Include /health and structured logging from the start",
                },
            ],
            "overall_risk": "high",
            "summary": "The spec covers basic CRUD but lacks authentication and observability.",
        }
    )


class TestStakeholderSimulator:
    """Tests for :class:`StakeholderSimulator`."""

    async def test_simulate_parses_valid_response(
        self,
        sample_spec: TaskSpec,
        review_response_json: str,
    ) -> None:
        """Simulator correctly parses a well-formed LLM JSON response."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(review_response_json)

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        assert isinstance(review, StakeholderReview)
        assert len(review.concerns) == 4
        assert review.overall_risk == "high"
        assert review.summary != ""

        roles = {c.role for c in review.concerns}
        assert "end_user" in roles
        assert "security_reviewer" in roles
        assert "product_manager" in roles
        assert "ops_engineer" in roles

    async def test_simulate_parses_severity(
        self,
        sample_spec: TaskSpec,
        review_response_json: str,
    ) -> None:
        """Each concern has a valid severity rating."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(review_response_json)

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        for concern in review.concerns:
            assert concern.severity in ("low", "medium", "high")

    async def test_simulate_handles_invalid_json(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Simulator returns empty review when LLM returns invalid JSON."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response("Not valid JSON at all!")

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        assert isinstance(review, StakeholderReview)
        assert len(review.concerns) == 0
        assert review.overall_risk == "low"

    async def test_simulate_handles_llm_exception(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Simulator returns empty review when LLM raises an exception."""
        client = AsyncMock(spec=LLMClient)
        client.generate.side_effect = RuntimeError("LLM unavailable")

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        assert isinstance(review, StakeholderReview)
        assert len(review.concerns) == 0
        assert review.overall_risk == "low"

    async def test_simulate_handles_code_fenced_response(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Simulator strips markdown code fences from LLM response."""
        inner_json = json.dumps(
            {
                "concerns": [],
                "overall_risk": "low",
                "summary": "Looks good.",
            }
        )
        fenced = f"```json\n{inner_json}\n```"
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(fenced)

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        assert review.summary == "Looks good."
        assert review.overall_risk == "low"

    async def test_simulate_empty_concerns(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Simulator handles a response with no concerns gracefully."""
        response_json = json.dumps(
            {
                "concerns": [],
                "overall_risk": "low",
                "summary": "No issues found.",
            }
        )
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(response_json)

        simulator = StakeholderSimulator(client)
        review = await simulator.simulate(sample_spec)

        assert len(review.concerns) == 0
        assert review.overall_risk == "low"
        assert review.summary == "No issues found."
