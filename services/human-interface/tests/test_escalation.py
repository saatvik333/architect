"""Tests for escalation decision logic."""

from __future__ import annotations

from human_interface.escalation import should_escalate
from human_interface.models import EscalationDecision


class TestShouldEscalate:
    """Verify all branches of the should_escalate() function."""

    def test_low_confidence_escalates(self) -> None:
        decision = EscalationDecision(confidence=0.3)
        assert should_escalate(decision) == "escalate"

    def test_confidence_at_threshold_escalates(self) -> None:
        """Confidence exactly at 0.6 should NOT trigger low-confidence escalate."""
        decision = EscalationDecision(confidence=0.6)
        # 0.6 is not < 0.6, so it should not be "escalate" for low confidence.
        result = should_escalate(decision)
        assert result != "escalate" or decision.is_security_critical

    def test_confidence_just_below_threshold(self) -> None:
        decision = EscalationDecision(confidence=0.59)
        assert should_escalate(decision) == "escalate"

    def test_security_critical_escalates(self) -> None:
        decision = EscalationDecision(confidence=0.95, is_security_critical=True)
        assert should_escalate(decision) == "escalate"

    def test_high_cost_impact_escalates(self) -> None:
        decision = EscalationDecision(confidence=0.95, cost_impact=300.0)
        assert should_escalate(decision, budget_total=1000.0) == "escalate"

    def test_cost_impact_at_threshold(self) -> None:
        """Exactly 20% of budget should NOT trigger (needs to be > 20%)."""
        decision = EscalationDecision(confidence=0.95, cost_impact=200.0)
        result = should_escalate(decision, budget_total=1000.0)
        assert result == "proceed"

    def test_cost_impact_zero_budget_skips(self) -> None:
        """When budget_total is 0, cost impact check is skipped."""
        decision = EscalationDecision(confidence=0.95, cost_impact=500.0)
        result = should_escalate(decision, budget_total=0.0)
        assert result == "proceed"

    def test_cost_impact_none_skips(self) -> None:
        """When cost_impact is None, cost impact check is skipped."""
        decision = EscalationDecision(confidence=0.95, cost_impact=None)
        result = should_escalate(decision, budget_total=1000.0)
        assert result == "proceed"

    def test_architectural_fork_escalates_with_options(self) -> None:
        decision = EscalationDecision(confidence=0.95, is_architectural_fork=True)
        assert should_escalate(decision) == "escalate_with_options"

    def test_medium_confidence_proceeds_with_flag(self) -> None:
        decision = EscalationDecision(confidence=0.75)
        assert should_escalate(decision) == "proceed_with_flag"

    def test_confidence_just_below_proceed(self) -> None:
        decision = EscalationDecision(confidence=0.89)
        assert should_escalate(decision) == "proceed_with_flag"

    def test_high_confidence_proceeds(self) -> None:
        decision = EscalationDecision(confidence=0.95)
        assert should_escalate(decision) == "proceed"

    def test_confidence_exactly_at_proceed_threshold(self) -> None:
        """Confidence exactly 0.9 should NOT trigger proceed_with_flag."""
        decision = EscalationDecision(confidence=0.9)
        assert should_escalate(decision) == "proceed"

    def test_priority_low_confidence_over_security(self) -> None:
        """Low confidence check comes before security check."""
        decision = EscalationDecision(confidence=0.3, is_security_critical=True)
        # Both would trigger "escalate", but low confidence is checked first.
        assert should_escalate(decision) == "escalate"

    def test_security_over_cost(self) -> None:
        """Security check comes before cost impact check."""
        decision = EscalationDecision(
            confidence=0.95,
            is_security_critical=True,
            cost_impact=500.0,
        )
        assert should_escalate(decision, budget_total=1000.0) == "escalate"

    def test_architectural_fork_over_proceed_with_flag(self) -> None:
        """Architectural fork check comes before medium-confidence flag."""
        decision = EscalationDecision(
            confidence=0.75,
            is_architectural_fork=True,
        )
        # 0.75 would normally be "proceed_with_flag" but arch fork is checked first.
        assert should_escalate(decision) == "escalate_with_options"

    def test_all_clear_proceed(self) -> None:
        decision = EscalationDecision(
            confidence=1.0,
            is_security_critical=False,
            cost_impact=0.0,
            is_architectural_fork=False,
        )
        assert should_escalate(decision, budget_total=10000.0) == "proceed"
