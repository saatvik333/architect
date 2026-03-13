"""Token cost tracking with per-model pricing breakdowns."""

from __future__ import annotations

from dataclasses import dataclass, field

# Pricing per token (USD) as of 2025-05 for Anthropic models.
# Format: {model_prefix: (input_cost_per_token, output_cost_per_token)}
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Tier 1 — Opus-class
    "claude-opus-4": (15.0 / 1_000_000, 75.0 / 1_000_000),
    # Tier 2 — Sonnet-class
    "claude-sonnet-4": (3.0 / 1_000_000, 15.0 / 1_000_000),
    # Tier 3 — Haiku-class
    "claude-haiku-3": (0.25 / 1_000_000, 1.25 / 1_000_000),
}

# Fallback pricing when model is not recognized (Sonnet-tier).
_DEFAULT_PRICING: tuple[float, float] = (3.0 / 1_000_000, 15.0 / 1_000_000)


def _resolve_pricing(model_id: str) -> tuple[float, float]:
    """Match a model_id to its pricing tier by prefix."""
    for prefix, pricing in _MODEL_PRICING.items():
        if model_id.startswith(prefix):
            return pricing
    return _DEFAULT_PRICING


@dataclass
class _ModelAccumulator:
    """Internal per-model accumulator."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0


@dataclass
class CostTracker:
    """Tracks cumulative token usage and cost across models.

    Thread-safety note: this class is designed for single-threaded async use.
    Each ``LLMClient`` instance should own its own ``CostTracker``.
    """

    _models: dict[str, _ModelAccumulator] = field(default_factory=dict)

    def record(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Record a single API call and return its cost in USD."""
        input_price, output_price = _resolve_pricing(model_id)
        cost = (input_tokens * input_price) + (output_tokens * output_price)

        acc = self._models.setdefault(model_id, _ModelAccumulator())
        acc.input_tokens += input_tokens
        acc.output_tokens += output_tokens
        acc.total_cost += cost
        acc.request_count += 1

        return cost

    @property
    def total_cost(self) -> float:
        """Total accumulated cost in USD across all models."""
        return sum(acc.total_cost for acc in self._models.values())

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output) across all models."""
        return sum(acc.input_tokens + acc.output_tokens for acc in self._models.values())

    def get_breakdown(self) -> dict[str, dict[str, float | int]]:
        """Per-model breakdown of usage and cost.

        Returns a dict keyed by model_id, each containing:
            input_tokens, output_tokens, total_cost, request_count
        """
        return {
            model_id: {
                "input_tokens": acc.input_tokens,
                "output_tokens": acc.output_tokens,
                "total_cost": acc.total_cost,
                "request_count": acc.request_count,
            }
            for model_id, acc in self._models.items()
        }
