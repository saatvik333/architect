"""Tests for the ScopeGovernor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse
from spec_engine.models import (
    AcceptanceCriterion,
    ScopeConstraints,
    ScopeReport,
    TaskSpec,
)
from spec_engine.scope_governor import ScopeGovernor


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
        intent="Build a notification microservice",
        constraints=["Must support email and SMS"],
        success_criteria=[
            AcceptanceCriterion(
                id="ac-test0001",
                description="Sends email notifications",
                test_type="integration",
            ),
            AcceptanceCriterion(
                id="ac-test0002",
                description="Sends SMS notifications",
                test_type="integration",
            ),
        ],
        file_targets=["src/notifications/email.py", "src/notifications/sms.py"],
        assumptions=["SMTP server available", "Twilio SDK"],
    )


@pytest.fixture
def mvp_report_json() -> str:
    return json.dumps(
        {
            "is_mvp": True,
            "deferred_features": ["Push notification support", "Notification templates"],
            "scope_creep_flags": [],
            "estimated_effort_hours": 16.0,
            "recommendations": [
                "Start with email only, add SMS in a follow-up iteration"
            ],
        }
    )


@pytest.fixture
def non_mvp_report_json() -> str:
    return json.dumps(
        {
            "is_mvp": False,
            "deferred_features": [
                "SMS support",
                "Push notifications",
                "Notification templates",
            ],
            "scope_creep_flags": [
                "Multiple delivery channels in one iteration",
                "Template engine adds significant complexity",
            ],
            "estimated_effort_hours": 60.0,
            "recommendations": [
                "Focus on email notifications first",
                "Break SMS into a separate task",
            ],
        }
    )


class TestScopeGovernor:
    """Tests for :class:`ScopeGovernor`."""

    async def test_evaluate_mvp_spec(
        self,
        sample_spec: TaskSpec,
        mvp_report_json: str,
    ) -> None:
        """Governor identifies an MVP-sized spec correctly."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(mvp_report_json)

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        assert isinstance(report, ScopeReport)
        assert report.is_mvp is True
        assert report.estimated_effort_hours == 16.0
        assert len(report.deferred_features) == 2
        assert len(report.scope_creep_flags) == 0
        assert len(report.recommendations) == 1

    async def test_evaluate_non_mvp_spec(
        self,
        sample_spec: TaskSpec,
        non_mvp_report_json: str,
    ) -> None:
        """Governor detects scope creep in a non-MVP spec."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(non_mvp_report_json)

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        assert report.is_mvp is False
        assert report.estimated_effort_hours == 60.0
        assert len(report.scope_creep_flags) == 2
        assert len(report.deferred_features) == 3

    async def test_evaluate_with_custom_constraints(
        self,
        sample_spec: TaskSpec,
        mvp_report_json: str,
    ) -> None:
        """Governor accepts custom scope constraints."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(mvp_report_json)

        constraints = ScopeConstraints(
            max_effort_hours=20.0,
            max_criteria=10,
            enforce_mvp=True,
        )

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec, constraints=constraints)

        assert isinstance(report, ScopeReport)
        # Verify the LLM was called (constraints are passed in the prompt)
        client.generate.assert_called_once()
        call_args = client.generate.call_args[0][0]
        assert "20.0" in call_args.messages[0]["content"]

    async def test_evaluate_handles_invalid_json(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Governor returns default report when LLM returns invalid JSON."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response("This is not JSON!")

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        assert isinstance(report, ScopeReport)
        assert report.is_mvp is True
        assert report.estimated_effort_hours == 0.0
        assert len(report.deferred_features) == 0

    async def test_evaluate_handles_llm_exception(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Governor returns default report when LLM raises an exception."""
        client = AsyncMock(spec=LLMClient)
        client.generate.side_effect = RuntimeError("LLM unavailable")

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        assert isinstance(report, ScopeReport)
        assert report.is_mvp is True
        assert report.estimated_effort_hours == 0.0

    async def test_evaluate_handles_code_fenced_response(
        self,
        sample_spec: TaskSpec,
    ) -> None:
        """Governor strips markdown code fences from LLM response."""
        inner_json = json.dumps(
            {
                "is_mvp": True,
                "deferred_features": [],
                "scope_creep_flags": [],
                "estimated_effort_hours": 4.0,
                "recommendations": ["Looks well-scoped"],
            }
        )
        fenced = f"```json\n{inner_json}\n```"
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(fenced)

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        assert report.is_mvp is True
        assert report.estimated_effort_hours == 4.0

    async def test_evaluate_default_constraints(
        self,
        sample_spec: TaskSpec,
        mvp_report_json: str,
    ) -> None:
        """Governor uses default constraints when none are provided."""
        client = AsyncMock(spec=LLMClient)
        client.generate.return_value = _make_llm_response(mvp_report_json)

        governor = ScopeGovernor(client)
        report = await governor.evaluate(sample_spec)

        # Verify defaults appeared in the prompt
        call_args = client.generate.call_args[0][0]
        assert "40.0" in call_args.messages[0]["content"]
        assert report.is_mvp is True
