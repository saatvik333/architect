"""Tests for Router."""

from __future__ import annotations

from architect_common.enums import ModelTier, TaskType
from architect_common.types import TaskId
from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.models import ComplexityScore
from multi_model_router.router import Router


class TestRouter:
    """Unit tests for the routing engine."""

    def test_low_complexity_routes_to_tier_3(self, task_router: Router) -> None:
        """A low-score task should route to TIER_3."""
        complexity = ComplexityScore(score=0.1, recommended_tier=ModelTier.TIER_3)
        decision = task_router.route(
            task_id=TaskId("task-test000001"),
            task_type=TaskType.REFACTOR,
            complexity=complexity,
        )
        assert decision.selected_tier == ModelTier.TIER_3

    def test_high_complexity_routes_to_tier_1(self, task_router: Router) -> None:
        """A high-score task should route to TIER_1."""
        complexity = ComplexityScore(score=0.85, recommended_tier=ModelTier.TIER_1)
        decision = task_router.route(
            task_id=TaskId("task-test000002"),
            task_type=TaskType.FIX_BUG,
            complexity=complexity,
        )
        assert decision.selected_tier == ModelTier.TIER_1

    def test_review_code_override_to_tier_1(self, task_router: Router) -> None:
        """REVIEW_CODE should always route to TIER_1 regardless of score."""
        complexity = ComplexityScore(score=0.1, recommended_tier=ModelTier.TIER_3)
        decision = task_router.route(
            task_id=TaskId("task-test000003"),
            task_type=TaskType.REVIEW_CODE,
            complexity=complexity,
        )
        assert decision.selected_tier == ModelTier.TIER_1
        assert decision.override_reason is not None
        assert "static override" in decision.override_reason

    def test_write_test_override_to_tier_3(self, task_router: Router) -> None:
        """WRITE_TEST should always route to TIER_3 regardless of score."""
        complexity = ComplexityScore(score=0.9, recommended_tier=ModelTier.TIER_1)
        decision = task_router.route(
            task_id=TaskId("task-test000004"),
            task_type=TaskType.WRITE_TEST,
            complexity=complexity,
        )
        assert decision.selected_tier == ModelTier.TIER_3
        assert decision.override_reason is not None

    def test_model_id_mapping(self, task_router: Router) -> None:
        """Each tier should map to the correct model ID."""
        for tier, expected_model in [
            (ModelTier.TIER_1, "claude-opus-4-20250514"),
            (ModelTier.TIER_2, "claude-sonnet-4-20250514"),
            (ModelTier.TIER_3, "claude-haiku-3-20250305"),
        ]:
            assert task_router._model_id_for_tier(tier) == expected_model

    def test_threshold_boundary(self) -> None:
        """Score exactly at a threshold boundary should route to the higher tier."""
        config = MultiModelRouterConfig(tier_1_threshold=0.7, tier_2_threshold=0.3)
        r = Router(config=config)

        # Exactly at tier_1 boundary
        at_t1 = ComplexityScore(score=0.7, recommended_tier=ModelTier.TIER_1)
        decision = r.route(TaskId("task-boundary01"), TaskType.FIX_BUG, at_t1)
        assert decision.selected_tier == ModelTier.TIER_1

        # Exactly at tier_2 boundary
        at_t2 = ComplexityScore(score=0.3, recommended_tier=ModelTier.TIER_2)
        decision = r.route(TaskId("task-boundary02"), TaskType.FIX_BUG, at_t2)
        assert decision.selected_tier == ModelTier.TIER_2

        # Just below tier_2 boundary
        below_t2 = ComplexityScore(score=0.29, recommended_tier=ModelTier.TIER_3)
        decision = r.route(TaskId("task-boundary03"), TaskType.FIX_BUG, below_t2)
        assert decision.selected_tier == ModelTier.TIER_3
