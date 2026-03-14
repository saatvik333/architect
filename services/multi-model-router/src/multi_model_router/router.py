"""Core routing logic — map tasks to model tiers."""

from __future__ import annotations

from architect_common.enums import ModelTier, TaskType
from architect_common.types import TaskId
from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.models import ComplexityScore, RoutingDecision

# ── Static model IDs per tier ────────────────────────────────────────
_TIER_MODELS: dict[ModelTier, str] = {
    ModelTier.TIER_1: "claude-opus-4-20250514",
    ModelTier.TIER_2: "claude-sonnet-4-20250514",
    ModelTier.TIER_3: "claude-haiku-3-20250305",
}

# ── Static task-type overrides ───────────────────────────────────────
_TASK_OVERRIDES: dict[TaskType, ModelTier] = {
    TaskType.REVIEW_CODE: ModelTier.TIER_1,
    TaskType.WRITE_TEST: ModelTier.TIER_3,
}


class Router:
    """Route tasks to the cheapest model tier that can handle them."""

    def __init__(self, config: MultiModelRouterConfig | None = None) -> None:
        self._config = config or MultiModelRouterConfig()

    def route(
        self,
        task_id: TaskId,
        task_type: TaskType,
        complexity: ComplexityScore,
    ) -> RoutingDecision:
        """Select a model tier for *task_id* based on its complexity.

        Static overrides (e.g. REVIEW_CODE always goes to TIER_1) are
        applied before the score-based threshold logic.
        """
        override_reason: str | None = None

        # Check static overrides first
        if task_type in _TASK_OVERRIDES:
            selected_tier = _TASK_OVERRIDES[task_type]
            override_reason = f"static override for {task_type.value}"
        elif complexity.score >= self._config.tier_1_threshold:
            selected_tier = ModelTier.TIER_1
        elif complexity.score >= self._config.tier_2_threshold:
            selected_tier = ModelTier.TIER_2
        else:
            selected_tier = ModelTier.TIER_3

        model_id = self._model_id_for_tier(selected_tier)

        return RoutingDecision(
            task_id=task_id,
            selected_tier=selected_tier,
            model_id=model_id,
            complexity=complexity,
            override_reason=override_reason,
        )

    def _model_id_for_tier(self, tier: ModelTier) -> str:
        """Return the concrete model identifier for *tier*."""
        return _TIER_MODELS[tier]
