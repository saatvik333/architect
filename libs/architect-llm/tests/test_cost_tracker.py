"""Tests for the CostTracker."""

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
