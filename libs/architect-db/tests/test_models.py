"""Basic model instantiation tests.

These tests verify that ORM models can be constructed without a live database.
They exercise column defaults and repr methods.
"""

from __future__ import annotations

from architect_common.types import (
    new_agent_id,
    new_event_id,
    new_proposal_id,
    new_task_id,
)
from architect_db.models.agent import AgentSession
from architect_db.models.base import Base
from architect_db.models.evaluation import EvaluationReport
from architect_db.models.event import EventLog
from architect_db.models.ledger import WorldStateLedger
from architect_db.models.proposal import Proposal
from architect_db.models.sandbox import SandboxAuditLog, SandboxSession
from architect_db.models.task import Task


class TestTaskModel:
    def test_create_task(self) -> None:
        task = Task(
            id=new_task_id(),
            type="implement_feature",
            status="pending",
            priority=5,
        )
        assert task.id.startswith("task-")
        assert task.type == "implement_feature"
        assert task.status == "pending"
        assert task.priority == 5

    def test_task_repr(self) -> None:
        task = Task(id="task-abc123", type="fix_bug", status="running")
        assert "task-abc123" in repr(task)
        assert "fix_bug" in repr(task)
        assert "running" in repr(task)

    def test_task_optional_fields_default_to_none(self) -> None:
        task = Task(id=new_task_id(), type="write_test", status="pending")
        assert task.agent_type is None
        assert task.model_tier is None
        assert task.assigned_agent is None
        assert task.inputs is None
        assert task.outputs is None
        assert task.dependencies is None
        assert task.dependents is None


class TestAgentSessionModel:
    def test_create_agent_session(self) -> None:
        session = AgentSession(
            id=new_agent_id(),
            agent_type="coder",
            model_tier="tier_2",
            status="running",
        )
        assert session.id.startswith("agent-")
        assert session.agent_type == "coder"
        assert session.model_tier == "tier_2"

    def test_agent_session_repr(self) -> None:
        session = AgentSession(
            id="agent-xyz", agent_type="reviewer", model_tier="tier_1", status="completed"
        )
        assert "agent-xyz" in repr(session)
        assert "reviewer" in repr(session)


class TestEventLogModel:
    def test_create_event(self) -> None:
        event = EventLog(
            id=new_event_id(),
            type="task.created",
            payload={"key": "value"},
        )
        assert event.id.startswith("evt-")
        assert event.type == "task.created"
        assert event.payload == {"key": "value"}

    def test_event_idempotency_key(self) -> None:
        event = EventLog(
            id=new_event_id(),
            type="task.started",
            idempotency_key="unique-key-123",
        )
        assert event.idempotency_key == "unique-key-123"


class TestProposalModel:
    def test_create_proposal(self) -> None:
        proposal = Proposal(
            id=new_proposal_id(),
            agent_id=new_agent_id(),
            task_id=new_task_id(),
            mutations={"add": {"file": "main.py"}},
            rationale="Implementing core feature",
            verdict="pending",
        )
        assert proposal.id.startswith("prop-")
        assert proposal.verdict == "pending"
        assert proposal.mutations is not None

    def test_proposal_repr(self) -> None:
        proposal = Proposal(id="prop-abc", verdict="accepted")
        assert "prop-abc" in repr(proposal)
        assert "accepted" in repr(proposal)


class TestWorldStateLedgerModel:
    def test_create_ledger_entry(self) -> None:
        entry = WorldStateLedger(
            version=1,
            state_snapshot={"tasks": {}, "agents": {}},
        )
        assert entry.version == 1
        assert entry.state_snapshot is not None

    def test_ledger_repr(self) -> None:
        entry = WorldStateLedger(version=42)
        assert "42" in repr(entry)


class TestSandboxModels:
    def test_create_sandbox_session(self) -> None:
        session = SandboxSession(
            id="sandbox-001",
            task_id=new_task_id(),
            status="creating",
            timeout_seconds=600,
        )
        assert session.status == "creating"
        assert session.timeout_seconds == 600

    def test_create_audit_log(self) -> None:
        log = SandboxAuditLog(
            id="audit-001",
            session_id="sandbox-001",
            command="python -m pytest",
            exit_code=0,
            stdout="3 passed",
            stderr="",
        )
        assert log.command == "python -m pytest"
        assert log.exit_code == 0


class TestEvaluationReportModel:
    def test_create_report(self) -> None:
        report = EvaluationReport(
            id="eval-001",
            task_id=new_task_id(),
            verdict="pass",
            layers_run=4,
            layer_results={
                "compilation": "pass",
                "unit_tests": "pass",
                "integration_tests": "pass",
                "adversarial": "pass",
            },
        )
        assert report.verdict == "pass"
        assert report.layers_run == 4

    def test_report_repr(self) -> None:
        report = EvaluationReport(id="eval-x", task_id="task-y", verdict="fail_soft")
        assert "eval-x" in repr(report)
        assert "task-y" in repr(report)
        assert "fail_soft" in repr(report)


class TestBaseMetadata:
    def test_all_tables_registered(self) -> None:
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "tasks",
            "agent_sessions",
            "event_log",
            "proposals",
            "world_state_ledger",
            "sandbox_sessions",
            "sandbox_audit_log",
            "evaluation_reports",
        }
        assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"
