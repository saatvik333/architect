"""Unified async LLM client wrapping the Anthropic SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

from architect_common.errors import LLMError, LLMRateLimitError, LLMResponseError

from .cost_tracker import CostTracker
from .models import LLMRequest, LLMResponse, TokenUsage
from .rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class LLMClient:
    """Async Claude API client with retry logic, cost tracking, and rate limiting.

    Usage::

        client = LLMClient(api_key="sk-...")
        try:
            response = await client.generate(request)
        finally:
            await client.close()
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        timeout: int = 120,
    ) -> None:
        self._default_model = default_model
        self._max_retries = max_retries
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=0,  # We handle retries ourselves for finer control.
            timeout=float(timeout),
        )
        self._cost_tracker = CostTracker()
        self._rate_limiter = TokenBucketRateLimiter()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a message to the Claude API and return a structured response.

        Handles retries on transient errors and rate-limit responses, tracks
        token usage, and enforces local rate limiting.

        Args:
            request: The LLM request parameters.

        Returns:
            A structured :class:`LLMResponse`.

        Raises:
            LLMRateLimitError: After exhausting retries on 429 responses.
            LLMResponseError: On unexpected API response shape.
            LLMError: On other API failures after retries.
        """
        model_id = request.model_id or self._default_model

        # Build the API kwargs.
        api_kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": request.messages,
        }
        if request.system_prompt:
            api_kwargs["system"] = request.system_prompt
        if request.tools is not None:
            api_kwargs["tools"] = request.tools
        if request.tool_choice is not None:
            api_kwargs["tool_choice"] = request.tool_choice

        # Estimate tokens for rate limiting (rough heuristic).
        estimated_tokens = request.max_tokens + sum(
            len(str(m.get("content", ""))) // 4 for m in request.messages
        )
        await self._rate_limiter.acquire(estimated_tokens)

        last_exception: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.messages.create(**api_kwargs)
                return self._parse_response(response, model_id)

            except anthropic.RateLimitError as exc:
                last_exception = exc
                logger.warning(
                    "Rate limited (attempt %d/%d): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt == self._max_retries:
                    raise LLMRateLimitError(
                        f"Rate limit exceeded after {self._max_retries} retries",
                        details={"model_id": model_id},
                    ) from exc
                # Back off before retrying.
                await asyncio.sleep(2**attempt)

            except anthropic.APIStatusError as exc:
                last_exception = exc
                # Retry on 5xx server errors.
                if exc.status_code >= 500 and attempt < self._max_retries:
                    logger.warning(
                        "Server error %d (attempt %d/%d): %s",
                        exc.status_code,
                        attempt,
                        self._max_retries,
                        exc,
                    )
                    await asyncio.sleep(2**attempt)
                    continue
                raise LLMError(
                    f"API error {exc.status_code}: {exc.message}",
                    details={"model_id": model_id, "status_code": exc.status_code},
                ) from exc

            except anthropic.APIConnectionError as exc:
                last_exception = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "Connection error (attempt %d/%d): %s",
                        attempt,
                        self._max_retries,
                        exc,
                    )
                    await asyncio.sleep(2**attempt)
                    continue
                raise LLMError(
                    "Failed to connect to Anthropic API",
                    details={"model_id": model_id},
                ) from exc

        # Should not reach here, but just in case.
        raise LLMError(
            "Exhausted retries",
            details={"model_id": model_id},
        ) from last_exception

    def _parse_response(
        self,
        response: anthropic.types.Message,
        model_id: str,
    ) -> LLMResponse:
        """Parse an Anthropic API message into our domain model."""
        # Track cost.
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._cost_tracker.record(model_id, input_tokens, output_tokens)

        # Extract text content and tool-use blocks.
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        content = "\n".join(text_parts)
        if not content and not tool_calls:
            raise LLMResponseError(
                "Empty response from model",
                details={"model_id": model_id, "stop_reason": response.stop_reason},
            )

        return LLMResponse(
            content=content,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=response.stop_reason or "unknown",
            tool_calls=tool_calls if tool_calls else None,
        )

    @property
    def total_usage(self) -> TokenUsage:
        """Accumulated token usage and estimated cost across all calls."""
        breakdown = self._cost_tracker.get_breakdown()
        total_input = sum(int(v["input_tokens"]) for v in breakdown.values())
        total_output = sum(int(v["output_tokens"]) for v in breakdown.values())
        return TokenUsage(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            estimated_cost_usd=self._cost_tracker.total_cost,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
