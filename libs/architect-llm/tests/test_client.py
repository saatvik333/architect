"""Tests for LLMClient budget enforcement and retry behaviour."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from architect_common.errors import BudgetExceededError
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest


def _make_request(content: str = "hello") -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": content}],
        max_tokens=100,
    )


def _make_api_response(
    text: str = "response",
    input_tokens: int = 10,
    output_tokens: int = 20,
    tool_calls: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock Anthropic Message response."""
    content_blocks = []

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    content_blocks.append(text_block)

    if tool_calls:
        for tc in tool_calls:
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.id = tc.get("id", "tool_1")
            tool_block.name = tc.get("name", "test_tool")
            tool_block.input = tc.get("input", {})
            content_blocks.append(tool_block)

    msg = MagicMock()
    msg.content = content_blocks
    msg.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    msg.stop_reason = "end_turn"
    return msg


@pytest.mark.asyncio
async def test_generate_rejected_when_budget_already_exceeded() -> None:
    """API call should be rejected *before* hitting the network when budget is exceeded."""
    client = LLMClient(api_key="test-key", max_budget_usd=0.0001)

    # Artificially inflate spending past the budget.
    client._cost_tracker.record(
        "claude-sonnet-4-20250514", input_tokens=100_000, output_tokens=50_000
    )

    with pytest.raises(BudgetExceededError):
        await client.generate(_make_request())

    await client.close()


@pytest.mark.asyncio
async def test_retry_stops_when_budget_exceeded_mid_retry() -> None:
    """Retry loop should stop early if budget is blown during retries."""
    # Use a generous budget so the pre-flight check passes; the mock will
    # raise BudgetExceededError on the *second* call (post-retry check).
    client = LLMClient(api_key="test-key", max_retries=3, max_budget_usd=100.0)

    # Simulate a rate-limit error on first attempt.
    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.headers = {}
    rate_limit_exc = anthropic.RateLimitError(
        message="rate limited",
        response=rate_limit_response,
        body=None,
    )

    call_count = 0

    async def _mock_create(**kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        raise rate_limit_exc

    client._client.messages.create = _mock_create  # type: ignore[assignment]

    check_call_count = 0

    def _budget_blow_on_retry(estimated_additional_cost: float = 0.0) -> None:
        nonlocal check_call_count
        check_call_count += 1
        # First call is the pre-flight check — let it pass.
        # Second call is the post-retry check — blow it up.
        if check_call_count > 1:
            raise BudgetExceededError(
                "Budget exceeded in retry",
                details={},
            )

    with (
        patch.object(client._cost_tracker, "check_budget", side_effect=_budget_blow_on_retry),
        patch("architect_llm.client.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BudgetExceededError, match="Budget exceeded in retry"),
    ):
        await client.generate(_make_request())

    # Should have only attempted one API call before the retry budget check stopped it.
    assert call_count == 1

    await client.close()


@pytest.mark.asyncio
async def test_tool_call_limit_exceeded() -> None:
    """Should raise BudgetExceededError when tool calls exceed max_tool_calls."""
    client = LLMClient(api_key="test-key", max_tool_calls=2)

    # Build a response with 5 tool calls.
    many_tools = [{"id": f"tool_{i}", "name": f"tool_{i}", "input": {}} for i in range(5)]
    mock_response = _make_api_response(tool_calls=many_tools)

    client._client.messages.create = AsyncMock(return_value=mock_response)  # type: ignore[assignment]

    with (
        patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock),
        pytest.raises(BudgetExceededError, match="tool calls"),
    ):
        await client.generate(_make_request())

    await client.close()


@pytest.mark.asyncio
async def test_generate_succeeds_within_budget() -> None:
    """Normal generate should work fine when within budget."""
    client = LLMClient(api_key="test-key", max_budget_usd=10.0)

    mock_response = _make_api_response()
    client._client.messages.create = AsyncMock(return_value=mock_response)  # type: ignore[assignment]

    with patch.object(client._rate_limiter, "acquire", new_callable=AsyncMock):
        result = await client.generate(_make_request())

    assert result.content == "response"
    assert result.stop_reason == "end_turn"

    await client.close()
