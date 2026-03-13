"""Pydantic request/response models for LLM interactions."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from architect_common.types import ArchitectBase


class LLMRequest(ArchitectBase):
    """Encapsulates a request to a Claude model."""

    model_id: str = "claude-sonnet-4-20250514"
    system_prompt: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    max_tokens: int = Field(default=16_000, ge=1)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None


class LLMResponse(ArchitectBase):
    """Structured response from a Claude model."""

    content: str
    model_id: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    stop_reason: str
    tool_calls: list[dict[str, Any]] | None = None


class TokenUsage(ArchitectBase):
    """Accumulated token usage summary."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
