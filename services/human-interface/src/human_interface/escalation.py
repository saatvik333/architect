"""Escalation decision logic for the Human Interface.

Determines whether a given agent decision should be escalated to a human
based on confidence, security criticality, cost impact, and whether it
represents an architectural fork.
"""

from __future__ import annotations

from human_interface.models import EscalationDecision


def should_escalate(decision: EscalationDecision, budget_total: float = 0.0) -> str:
    """Determine the escalation action for a decision.

    Returns one of:
    - ``"escalate"`` — requires human intervention before proceeding.
    - ``"escalate_with_options"`` — present architectural options to the human.
    - ``"proceed_with_flag"`` — agent may proceed but flag for later review.
    - ``"proceed"`` — no escalation needed.

    Args:
        decision: The decision parameters to evaluate.
        budget_total: The total project budget (tokens or USD) for cost
            impact comparison.  When ``0.0`` the cost-impact check is skipped.

    Returns:
        Action string indicating the escalation outcome.
    """
    if decision.confidence < 0.6:
        return "escalate"

    if decision.is_security_critical:
        return "escalate"

    if (
        decision.cost_impact is not None
        and budget_total > 0
        and decision.cost_impact > budget_total * 0.2
    ):
        return "escalate"

    if decision.is_architectural_fork:
        return "escalate_with_options"

    if decision.confidence < 0.9:
        return "proceed_with_flag"

    return "proceed"
