"""Tests for the CostTracker."""

from unittest.mock import patch

import pytest

from architect_common.errors import BudgetExceededError
from architect_llm.cost_tracker import CostTracker


def test_record_returns_cost() -> None:
    tracker = CostTracker()
    cost = tracker.record("claude-sonnet-4-20250514", input_tokens=1000, output_tokens=500)
    # Sonnet: input $3/M, output $15/M
    expected = (1000 * 3.0 / 1_000_000) + (500 * 15.0 / 1_000_000)
    assert abs(cost - expected) < 1e-12


def test_total_cost_accumulates() -> None:
    tracker = CostTracker()
    tracker.record("claude-sonnet-4-20250514", input_tokens=1000, output_tokens=500)
    tracker.record("claude-sonnet-4-20250514", input_tokens=2000, output_tokens=1000)

    expected = (3000 * 3.0 / 1_000_000) + (1500 * 15.0 / 1_000_000)
    assert abs(tracker.total_cost - expected) < 1e-12


def test_total_tokens() -> None:
    tracker = CostTracker()
    tracker.record("claude-sonnet-4-20250514", input_tokens=100, output_tokens=50)
    tracker.record("claude-opus-4-20250514", input_tokens=200, output_tokens=100)
    assert tracker.total_tokens == 450


def test_opus_pricing() -> None:
    tracker = CostTracker()
    cost = tracker.record("claude-opus-4-20250514", input_tokens=1000, output_tokens=1000)
    # Opus: input $15/M, output $75/M
    expected = (1000 * 15.0 / 1_000_000) + (1000 * 75.0 / 1_000_000)
    assert abs(cost - expected) < 1e-12


def test_haiku_pricing() -> None:
    tracker = CostTracker()
    cost = tracker.record("claude-haiku-3-20250514", input_tokens=10_000, output_tokens=5_000)
    # Haiku: input $0.25/M, output $1.25/M
    expected = (10_000 * 0.25 / 1_000_000) + (5_000 * 1.25 / 1_000_000)
    assert abs(cost - expected) < 1e-12


def test_unknown_model_uses_default_pricing() -> None:
    tracker = CostTracker()
    cost = tracker.record("some-unknown-model", input_tokens=1000, output_tokens=1000)
    # Default is Sonnet-tier pricing
    expected = (1000 * 3.0 / 1_000_000) + (1000 * 15.0 / 1_000_000)
    assert abs(cost - expected) < 1e-12


def test_get_breakdown_per_model() -> None:
    tracker = CostTracker()
    tracker.record("claude-sonnet-4-20250514", input_tokens=100, output_tokens=50)
    tracker.record("claude-opus-4-20250514", input_tokens=200, output_tokens=100)
    tracker.record("claude-sonnet-4-20250514", input_tokens=300, output_tokens=150)

    breakdown = tracker.get_breakdown()
    assert set(breakdown.keys()) == {"claude-sonnet-4-20250514", "claude-opus-4-20250514"}

    sonnet = breakdown["claude-sonnet-4-20250514"]
    assert sonnet["input_tokens"] == 400
    assert sonnet["output_tokens"] == 200
    assert sonnet["request_count"] == 2

    opus = breakdown["claude-opus-4-20250514"]
    assert opus["input_tokens"] == 200
    assert opus["output_tokens"] == 100
    assert opus["request_count"] == 1


def test_empty_tracker() -> None:
    tracker = CostTracker()
    assert tracker.total_cost == 0.0
    assert tracker.total_tokens == 0
    assert tracker.get_breakdown() == {}


# ── Budget enforcement tests ────────────────────────────────────


def test_check_budget_passes_when_under_limit() -> None:
    tracker = CostTracker(max_budget_usd=1.0)
    # Spend a small amount, then check — should not raise.
    tracker.record("claude-sonnet-4-20250514", input_tokens=100, output_tokens=50)
    tracker.check_budget()  # No exception expected.


def test_check_budget_raises_when_over_limit() -> None:
    tracker = CostTracker(max_budget_usd=0.0001)
    # Record enough to push over the tiny budget.
    tracker.record("claude-sonnet-4-20250514", input_tokens=10_000, output_tokens=5_000)
    with pytest.raises(BudgetExceededError, match="Budget exceeded"):
        tracker.check_budget()


def test_check_budget_raises_with_estimated_additional_cost() -> None:
    tracker = CostTracker(max_budget_usd=0.01)
    # Current spend is zero, but estimated cost exceeds budget.
    with pytest.raises(BudgetExceededError, match="Budget exceeded"):
        tracker.check_budget(estimated_additional_cost=0.02)


def test_check_budget_passes_when_no_limit() -> None:
    tracker = CostTracker(max_budget_usd=None)
    # Record a lot — should never raise because there's no limit.
    tracker.record("claude-opus-4-20250514", input_tokens=1_000_000, output_tokens=500_000)
    tracker.check_budget()  # No exception expected.
    tracker.check_budget(estimated_additional_cost=100.0)  # Still no exception.


def test_check_budget_warns_at_75_percent(caplog: pytest.LogCaptureFixture) -> None:
    tracker = CostTracker(max_budget_usd=1.0)
    # Sonnet pricing: input $3/M, output $15/M
    # We need total_cost / 1.0 >= 0.75
    # 50_000 input + 50_000 output = (50k * 3/M) + (50k * 15/M) = 0.15 + 0.75 = 0.90
    # That's 90%, let's aim for ~78%: 40k input + 40k output = 0.12 + 0.60 = 0.72 ... too low
    # 42k input + 42k output = 0.126 + 0.63 = 0.756 — 75.6%
    tracker.record("claude-sonnet-4-20250514", input_tokens=42_000, output_tokens=42_000)
    with patch("architect_llm.cost_tracker.logger") as mock_logger:
        tracker.check_budget()
        mock_logger.warning.assert_called_once()
        assert "75%" in mock_logger.warning.call_args[0][0]


def test_check_budget_warns_at_90_percent() -> None:
    tracker = CostTracker(max_budget_usd=1.0)
    # 50k input + 50k output = 0.15 + 0.75 = 0.90 — exactly 90%
    tracker.record("claude-sonnet-4-20250514", input_tokens=50_000, output_tokens=50_000)
    with patch("architect_llm.cost_tracker.logger") as mock_logger:
        tracker.check_budget()
        mock_logger.warning.assert_called_once()
        assert "90%" in mock_logger.warning.call_args[0][0]
