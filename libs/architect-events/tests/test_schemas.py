"""Tests for event schemas and serialization round-tripping."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from architect_common.enums import (
    AgentType,
    EvalVerdict,
    EventType,
    ModelTier,
    TaskType,
)
from architect_common.types import (
    AgentId,
    LedgerVersion,
    ProposalId,
    TaskId,
    new_event_id,
)
from architect_events.schemas import (
    AgentCompletedEvent,
    AgentSpawnedEvent,
    BudgetWarningEvent,
    EvalCompletedEvent,
    EventEnvelope,
    ProposalAcceptedEvent,
    ProposalCreatedEvent,
    ProposalRejectedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
)
from architect_events.serialization import deserialize_event, serialize_event


# ── EventEnvelope ───────────────────────────────────────────────────
class TestEventEnvelope:
    def test_defaults(self) -> None:
        env = EventEnvelope(type=EventType.TASK_CREATED)
        assert env.id.startswith("evt-")
        assert env.type == EventType.TASK_CREATED
        assert isinstance(env.timestamp, datetime)
        assert env.correlation_id is None
        assert env.payload == {}

    def test_custom_fields(self) -> None:
        eid = new_event_id()
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        env = EventEnvelope(
            id=eid,
            type=EventType.AGENT_SPAWNED,
            timestamp=ts,
            correlation_id="corr-123",
            payload={"key": "value"},
        )
        assert env.id == eid
        assert env.timestamp == ts
        assert env.correlation_id == "corr-123"
        assert env.payload == {"key": "value"}

    def test_is_frozen(self) -> None:
        env = EventEnvelope(type=EventType.TASK_CREATED)
        try:
            env.type = EventType.TASK_FAILED  # type: ignore[misc]
            raised = False
        except Exception:
            raised = True
        assert raised


# ── Task events ─────────────────────────────────────────────────────
class TestTaskEvents:
    def test_task_created(self) -> None:
        evt = TaskCreatedEvent(
            task_id=TaskId("task-abc123"),
            task_type=TaskType.IMPLEMENT_FEATURE,
            agent_type=AgentType.CODER,
        )
        assert evt.task_id == "task-abc123"
        assert evt.task_type == TaskType.IMPLEMENT_FEATURE
        assert evt.agent_type == AgentType.CODER

    def test_task_started(self) -> None:
        evt = TaskStartedEvent(
            task_id=TaskId("task-abc123"),
            agent_id=AgentId("agent-xyz789"),
        )
        assert evt.task_id == "task-abc123"
        assert evt.agent_id == "agent-xyz789"

    def test_task_completed(self) -> None:
        evt = TaskCompletedEvent(
            task_id=TaskId("task-abc123"),
            agent_id=AgentId("agent-xyz789"),
            verdict=EvalVerdict.PASS,
        )
        assert evt.verdict == EvalVerdict.PASS

    def test_task_failed(self) -> None:
        evt = TaskFailedEvent(
            task_id=TaskId("task-abc123"),
            agent_id=AgentId("agent-xyz789"),
            error_message="Compilation error in foo.py",
        )
        assert evt.error_message == "Compilation error in foo.py"


# ── Proposal events ────────────────────────────────────────────────
class TestProposalEvents:
    def test_proposal_created(self) -> None:
        evt = ProposalCreatedEvent(
            proposal_id=ProposalId("prop-aaa111"),
            agent_id=AgentId("agent-xyz789"),
            task_id=TaskId("task-abc123"),
        )
        assert evt.proposal_id == "prop-aaa111"

    def test_proposal_accepted(self) -> None:
        evt = ProposalAcceptedEvent(
            proposal_id=ProposalId("prop-aaa111"),
            ledger_version=LedgerVersion(42),
        )
        assert evt.ledger_version == 42

    def test_proposal_rejected(self) -> None:
        evt = ProposalRejectedEvent(
            proposal_id=ProposalId("prop-aaa111"),
            reason="Failed adversarial layer",
        )
        assert evt.reason == "Failed adversarial layer"


# ── Agent events ───────────────────────────────────────────────────
class TestAgentEvents:
    def test_agent_spawned(self) -> None:
        evt = AgentSpawnedEvent(
            agent_id=AgentId("agent-xyz789"),
            agent_type=AgentType.CODER,
            model_tier=ModelTier.TIER_2,
            task_id=TaskId("task-abc123"),
        )
        assert evt.model_tier == ModelTier.TIER_2
        assert evt.task_id == "task-abc123"

    def test_agent_completed(self) -> None:
        evt = AgentCompletedEvent(
            agent_id=AgentId("agent-xyz789"),
            tokens_consumed=15_000,
        )
        assert evt.tokens_consumed == 15_000


# ── Eval events ────────────────────────────────────────────────────
class TestEvalEvents:
    def test_eval_completed(self) -> None:
        evt = EvalCompletedEvent(
            task_id=TaskId("task-abc123"),
            verdict=EvalVerdict.FAIL_SOFT,
            layer_results=[
                {"layer": "compilation", "passed": True},
                {"layer": "unit_tests", "passed": False},
            ],
        )
        assert evt.verdict == EvalVerdict.FAIL_SOFT
        assert len(evt.layer_results) == 2


# ── Budget events ──────────────────────────────────────────────────
class TestBudgetEvents:
    def test_budget_warning(self) -> None:
        evt = BudgetWarningEvent(consumed_pct=82.5, remaining_tokens=175_000)
        assert evt.consumed_pct == 82.5
        assert evt.remaining_tokens == 175_000


# ── Serialization round-trip ───────────────────────────────────────
class TestSerialization:
    def test_round_trip(self) -> None:
        original = EventEnvelope(
            type=EventType.TASK_CREATED,
            correlation_id="corr-roundtrip",
            payload={"task_id": "task-abc123", "task_type": "implement_feature"},
        )
        wire = serialize_event(original)
        assert isinstance(wire, dict)
        assert "data" in wire
        # Simulate what Redis returns: bytes keys and values.
        redis_data: dict[bytes, bytes] = {k.encode(): v.encode() for k, v in wire.items()}
        restored = deserialize_event(redis_data)
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.correlation_id == original.correlation_id
        assert restored.payload == original.payload

    def test_serialize_produces_valid_json(self) -> None:
        env = EventEnvelope(type=EventType.BUDGET_WARNING)
        wire = serialize_event(env)
        parsed = json.loads(wire["data"])
        assert parsed["type"] == "budget.warning"
        assert "id" in parsed
        assert "timestamp" in parsed
