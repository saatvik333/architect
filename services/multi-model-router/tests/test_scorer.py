"""Tests for ComplexityScorer."""

from __future__ import annotations

from architect_common.enums import ModelTier, TaskType
from multi_model_router.scorer import ComplexityScorer


class TestComplexityScorer:
    """Unit tests for the complexity scoring engine."""

    def test_review_code_scores_high(self, scorer: ComplexityScorer) -> None:
        """REVIEW_CODE has a high task-type weight and should produce a mid-to-high score."""
        result = scorer.score(TaskType.REVIEW_CODE, "Review the authentication module")
        assert result.score >= 0.3
        assert result.factors["task_type"] == 0.8

    def test_write_test_scores_low(self, scorer: ComplexityScorer) -> None:
        """WRITE_TEST has the lowest task-type weight."""
        result = scorer.score(TaskType.WRITE_TEST, "Write unit tests")
        assert result.score < 0.3
        assert result.factors["task_type"] == 0.2

    def test_high_token_estimate_increases_score(self, scorer: ComplexityScorer) -> None:
        """A large token estimate should push the score upward."""
        low = scorer.score(TaskType.REFACTOR, "Refactor module", token_estimate=0)
        high = scorer.score(TaskType.REFACTOR, "Refactor module", token_estimate=100_000)
        assert high.score > low.score
        assert high.factors["token_estimate"] == 1.0

    def test_zero_tokens_factor_is_zero(self, scorer: ComplexityScorer) -> None:
        """Zero or negative token estimate should yield 0.0 token factor."""
        result = scorer.score(TaskType.WRITE_TEST, "Test", token_estimate=0)
        assert result.factors["token_estimate"] == 0.0

    def test_huge_token_estimate_caps_at_one(self, scorer: ComplexityScorer) -> None:
        """Token estimates beyond 100k should still cap at 1.0."""
        result = scorer.score(TaskType.REFACTOR, "Refactor", token_estimate=500_000)
        assert result.factors["token_estimate"] == 1.0

    def test_keywords_increase_score(self, scorer: ComplexityScorer) -> None:
        """Complex-domain keywords should increase the keyword factor."""
        without = scorer.score(TaskType.IMPLEMENT_FEATURE, "Add a button")
        with_kw = scorer.score(
            TaskType.IMPLEMENT_FEATURE,
            "Add a button",
            keywords=["security", "concurrent"],
        )
        assert with_kw.score > without.score
        assert with_kw.factors["keywords"] > 0.0

    def test_long_description_increases_score(self, scorer: ComplexityScorer) -> None:
        """A longer description should yield a higher description factor."""
        short = scorer.score(TaskType.FIX_BUG, "Fix it")
        long_desc = "Fix the race condition in " + "x " * 300
        long = scorer.score(TaskType.FIX_BUG, long_desc)
        assert long.factors["description"] > short.factors["description"]

    def test_empty_description(self, scorer: ComplexityScorer) -> None:
        """An empty description should still produce a valid score."""
        result = scorer.score(TaskType.REFACTOR, "")
        assert 0.0 <= result.score <= 1.0
        assert result.factors["description"] == 0.1

    def test_recommended_tier_follows_score(self, scorer: ComplexityScorer) -> None:
        """The recommended_tier should match the score thresholds."""
        # Low complexity
        low = scorer.score(TaskType.WRITE_TEST, "test", token_estimate=0)
        assert low.recommended_tier == ModelTier.TIER_3

        # High complexity
        high = scorer.score(
            TaskType.REVIEW_CODE,
            "Review the distributed security architecture for the cryptography module",
            token_estimate=80_000,
            keywords=["security", "concurrent", "distributed"],
        )
        assert high.recommended_tier == ModelTier.TIER_1
