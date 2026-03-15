"""Tests for LLM request/response Pydantic models."""

import pytest
from pydantic import ValidationError

from architect_llm.models import LLMRequest, LLMResponse, TokenUsage

# ── LLMRequest ────────────────────────────────────────────────────────


def test_request_defaults() -> None:
    req = LLMRequest()
    assert req.model_id == "claude-sonnet-4-20250514"
    assert req.system_prompt == ""
    assert req.messages == []
    assert req.max_tokens == 16_000
    assert req.temperature == 0.2
    assert req.tools is None
    assert req.tool_choice is None


def test_request_with_messages() -> None:
    req = LLMRequest(
        model_id="claude-opus-4-20250514",
        system_prompt="You are helpful.",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=8000,
        temperature=0.5,
    )
    assert req.model_id == "claude-opus-4-20250514"
    assert len(req.messages) == 1
    assert req.messages[0]["role"] == "user"


def test_request_with_tools() -> None:
    tool = {
        "name": "read_file",
        "description": "Read a file from disk",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    }
    req = LLMRequest(tools=[tool], tool_choice={"type": "auto"})
    assert req.tools is not None
    assert len(req.tools) == 1
    assert req.tool_choice == {"type": "auto"}


def test_request_is_frozen() -> None:
    req = LLMRequest()
    with pytest.raises(ValidationError):
        req.model_id = "something-else"  # type: ignore[misc]


def test_request_temperature_range() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(temperature=1.5)

    with pytest.raises(ValidationError):
        LLMRequest(temperature=-0.1)


def test_request_max_tokens_minimum() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(max_tokens=0)


# ── LLMResponse ───────────────────────────────────────────────────────


def test_response_basic() -> None:
    resp = LLMResponse(
        content="Hello, world!",
        model_id="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )
    assert resp.content == "Hello, world!"
    assert resp.stop_reason == "end_turn"
    assert resp.tool_calls is None


def test_response_with_tool_calls() -> None:
    resp = LLMResponse(
        content="",
        model_id="claude-sonnet-4-20250514",
        input_tokens=200,
        output_tokens=100,
        stop_reason="tool_use",
        tool_calls=[
            {"id": "call_1", "name": "read_file", "input": {"path": "/tmp/foo.py"}},  # nosec B108
        ],
    )
    assert resp.tool_calls is not None
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["name"] == "read_file"


def test_response_is_frozen() -> None:
    resp = LLMResponse(
        content="test",
        model_id="m",
        input_tokens=0,
        output_tokens=0,
        stop_reason="end_turn",
    )
    with pytest.raises(ValidationError):
        resp.content = "changed"  # type: ignore[misc]


def test_response_tokens_non_negative() -> None:
    with pytest.raises(ValidationError):
        LLMResponse(
            content="test",
            model_id="m",
            input_tokens=-1,
            output_tokens=0,
            stop_reason="end_turn",
        )


# ── TokenUsage ────────────────────────────────────────────────────────


def test_token_usage_defaults() -> None:
    usage = TokenUsage()
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 0
    assert usage.estimated_cost_usd == 0.0


def test_token_usage_with_values() -> None:
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        estimated_cost_usd=0.015,
    )
    assert usage.input_tokens == 1000
    assert usage.total_tokens == 1500


def test_token_usage_is_frozen() -> None:
    usage = TokenUsage()
    with pytest.raises(ValidationError):
        usage.input_tokens = 42  # type: ignore[misc]


def test_token_usage_non_negative() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1)

    with pytest.raises(ValidationError):
        TokenUsage(estimated_cost_usd=-0.01)
