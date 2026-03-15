"""In-memory cost tracking for routing decisions."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from architect_common.enums import ModelTier
from architect_llm.cost_tracker import _resolve_pricing
from multi_model_router.models import (
    CostSavingsReport,
    CostSummary,
    RoutingDecision,
    RoutingStats,
    TierCost,
)
from multi_model_router.router import _TIER_MODELS

logger = structlog.get_logger()

# The Tier 1 model ID used for hypothetical cost comparison.
_TIER_1_MODEL_ID = _TIER_MODELS[ModelTier.TIER_1]


@dataclass
class _TierAccumulator:
    """Internal per-tier accumulator."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0


@dataclass
class CostCollector:
    """Tracks routing costs in-memory, aggregated by tier.

    Thread-safety note: designed for single-threaded async use within one
    FastAPI process.
    """

    _tiers: dict[ModelTier, _TierAccumulator] = field(default_factory=dict)
    _total_requests: int = 0
    _complexity_sum: float = 0.0
    _escalation_count: int = 0
    _hypothetical_tier1_cost: float = 0.0

    def record_routing(
        self,
        decision: RoutingDecision,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Record a routing event and return its cost in USD.

        Also computes the hypothetical Tier 1 cost for the same token
        counts, so savings can be calculated later.
        """
        # Actual cost using the selected model
        input_price, output_price = _resolve_pricing(decision.model_id)
        cost = (input_tokens * input_price) + (output_tokens * output_price)

        acc = self._tiers.setdefault(decision.selected_tier, _TierAccumulator())
        acc.input_tokens += input_tokens
        acc.output_tokens += output_tokens
        acc.total_cost_usd += cost
        acc.request_count += 1

        # Hypothetical Tier 1 cost
        t1_input, t1_output = _resolve_pricing(_TIER_1_MODEL_ID)
        self._hypothetical_tier1_cost += (input_tokens * t1_input) + (
            output_tokens * t1_output
        )

        # Bookkeeping
        self._total_requests += 1
        self._complexity_sum += decision.complexity.score

        logger.debug(
            "cost_recorded",
            task_id=decision.task_id,
            tier=decision.selected_tier.value,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return cost

    def record_escalation(self) -> None:
        """Increment the escalation counter."""
        self._escalation_count += 1

    def get_cost_summary(self) -> CostSummary:
        """Return aggregated cost information across all tiers."""
        tier_costs: list[TierCost] = []
        total_cost = 0.0

        for tier in (ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3):
            acc = self._tiers.get(tier)
            if acc is None:
                continue
            tier_costs.append(
                TierCost(
                    tier=tier,
                    total_tokens=acc.input_tokens + acc.output_tokens,
                    input_tokens=acc.input_tokens,
                    output_tokens=acc.output_tokens,
                    total_cost_usd=round(acc.total_cost_usd, 8),
                )
            )
            total_cost += acc.total_cost_usd

        return CostSummary(
            total_cost_usd=round(total_cost, 8),
            cost_by_tier=tier_costs,
            total_requests=self._total_requests,
        )

    def get_cost_savings(self) -> CostSavingsReport:
        """Compare actual spend to hypothetical all-Tier-1 spend."""
        actual = sum(acc.total_cost_usd for acc in self._tiers.values())
        hypothetical = self._hypothetical_tier1_cost
        savings = hypothetical - actual
        percentage = (savings / hypothetical * 100.0) if hypothetical > 0 else 0.0

        return CostSavingsReport(
            actual_cost_usd=round(actual, 8),
            hypothetical_all_tier1_cost_usd=round(hypothetical, 8),
            savings_usd=round(savings, 8),
            savings_percentage=round(percentage, 2),
        )

    def get_stats(self) -> RoutingStats:
        """Return aggregate routing statistics including cost data."""
        avg_complexity = (
            self._complexity_sum / self._total_requests
            if self._total_requests > 0
            else 0.0
        )
        tier_distribution: dict[str, int] = {}
        total_cost = 0.0
        for tier, acc in self._tiers.items():
            if acc.request_count > 0:
                tier_distribution[tier.value] = acc.request_count
            total_cost += acc.total_cost_usd

        savings = self._hypothetical_tier1_cost - total_cost

        return RoutingStats(
            total_requests=self._total_requests,
            tier_distribution=tier_distribution,
            escalation_count=self._escalation_count,
            average_complexity=round(avg_complexity, 4),
            total_cost_usd=round(total_cost, 8),
            estimated_savings_usd=round(max(savings, 0.0), 8),
        )
