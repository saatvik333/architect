"""Tests for Human Interface domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from architect_common.enums import (
    ApprovalGateStatus,
    EscalationCategory,
    EscalationSeverity,
    EscalationStatus,
)
from architect_common.types import AgentId, ApprovalGateId, EscalationId, TaskId
from human_interface.models import (
    ActivityEvent,
    ApprovalGateResponse,
    CreateApprovalGateRequest,
    CreateEscalationRequest,
    EscalationDecision,
    EscalationOption,
    EscalationResponse,
    EscalationStatsResponse,
    ProgressSummary,
    ResolveEscalationRequest,
    VoteRequest,
    WebSocketMessage,
)


class TestModels:
    """Verify domain models are frozen and validate correctly."""

    def test_escalation_option_frozen(self) -> None:
        opt = EscalationOption(label="Option A", description="Do X", tradeoff="Slower")
        with pytest.raises(ValidationError):
            opt.label = "Changed"  # type: ignore[misc]

    def test_escalation_option_creation(self) -> None:
        opt = EscalationOption(label="Refactor", description="Clean up the code", tradeoff="Time")
        assert opt.label == "Refactor"
        assert opt.description == "Clean up the code"
        assert opt.tradeoff == "Time"

    def test_escalation_decision_creation(self) -> None:
        dec = EscalationDecision(
            confidence=0.5,
            is_security_critical=True,
            cost_impact=1000.0,
            is_architectural_fork=False,
        )
        assert dec.confidence == 0.5
        assert dec.is_security_critical is True

    def test_escalation_decision_frozen(self) -> None:
        dec = EscalationDecision(confidence=0.8)
        with pytest.raises(ValidationError):
            dec.confidence = 0.9  # type: ignore[misc]

    def test_create_escalation_request(self) -> None:
        req = CreateEscalationRequest(
            source_agent_id=AgentId("agent-001"),
            source_task_id=TaskId("task-001"),
            summary="Need clarification",
            category=EscalationCategory.CONFIDENCE,
            severity=EscalationSeverity.MEDIUM,
        )
        assert req.summary == "Need clarification"
        assert req.category == EscalationCategory.CONFIDENCE

    def test_resolve_escalation_request(self) -> None:
        req = ResolveEscalationRequest(
            resolved_by="human-operator",
            resolution="approved",
            custom_input={"note": "Looks good"},
        )
        assert req.resolved_by == "human-operator"
        assert req.custom_input is not None

    def test_escalation_response_defaults(self) -> None:
        resp = EscalationResponse(
            id=EscalationId("esc-test"),
            summary="Test escalation",
            category=EscalationCategory.SECURITY,
            severity=EscalationSeverity.HIGH,
        )
        assert resp.status == EscalationStatus.PENDING
        assert resp.resolved_by is None
        assert resp.options == []

    def test_escalation_response_frozen(self) -> None:
        resp = EscalationResponse(
            id=EscalationId("esc-test"),
            summary="Test",
            category=EscalationCategory.BUDGET,
            severity=EscalationSeverity.LOW,
        )
        with pytest.raises(ValidationError):
            resp.status = EscalationStatus.RESOLVED  # type: ignore[misc]

    def test_escalation_stats_response(self) -> None:
        stats = EscalationStatsResponse(
            total=10,
            pending=3,
            resolved=5,
            expired=2,
            by_category={"confidence": 4, "security": 6},
            by_severity={"low": 2, "high": 8},
        )
        assert stats.total == 10
        assert stats.by_category["confidence"] == 4

    def test_create_approval_gate_request(self) -> None:
        req = CreateApprovalGateRequest(
            action_type="deploy",
            resource_id="proj-001",
            required_approvals=2,
            context={"environment": "prod"},
        )
        assert req.action_type == "deploy"
        assert req.required_approvals == 2

    def test_vote_request(self) -> None:
        vote = VoteRequest(voter="alice", decision="approve", comment="LGTM")
        assert vote.voter == "alice"
        assert vote.decision == "approve"

    def test_vote_request_deny(self) -> None:
        vote = VoteRequest(voter="bob", decision="deny")
        assert vote.decision == "deny"
        assert vote.comment is None

    def test_approval_gate_response_defaults(self) -> None:
        resp = ApprovalGateResponse(
            id=ApprovalGateId("gate-test"),
            action_type="merge",
        )
        assert resp.status == ApprovalGateStatus.PENDING
        assert resp.current_approvals == 0
        assert resp.required_approvals == 1

    def test_progress_summary_defaults(self) -> None:
        prog = ProgressSummary()
        assert prog.project_name == "ARCHITECT"
        assert prog.status == "running"
        assert prog.completion_pct == 0.0
        assert prog.recent_events == []

    def test_progress_summary_with_data(self) -> None:
        prog = ProgressSummary(
            tasks_completed=5,
            tasks_total=10,
            completion_pct=50.0,
            budget_consumed_pct=30.0,
            tests_passing=42,
            tests_failing=3,
            coverage_pct=85.5,
            blockers=[],
        )
        assert prog.tasks_completed == 5
        assert prog.blockers == []

    def test_activity_event(self) -> None:
        evt = ActivityEvent(
            id="evt-001",
            type="task.completed",
            summary="Task finished",
        )
        assert evt.type == "task.completed"
        assert evt.payload == {}

    def test_websocket_message(self) -> None:
        msg = WebSocketMessage(
            type="escalation_created",
            data={"id": "esc-001"},
        )
        assert msg.type == "escalation_created"
        assert msg.data["id"] == "esc-001"

    def test_websocket_message_frozen(self) -> None:
        msg = WebSocketMessage(type="test")
        with pytest.raises(ValidationError):
            msg.type = "changed"  # type: ignore[misc]
