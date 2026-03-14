"""Factory functions that create test instances of domain objects.

Every factory returns a plain dict with sensible defaults that can be
overridden via keyword arguments, making tests concise and readable.
"""

from __future__ import annotations

from typing import Any

from architect_common.enums import (
    AgentType,
    EvalVerdict,
    EventType,
    ModelTier,
    ProposalVerdict,
    StatusEnum,
    TaskType,
)
from architect_common.types import (
    AgentId,
    TaskId,
    new_agent_id,
    new_event_id,
    new_proposal_id,
    new_task_id,
    utcnow,
)


def make_task_id() -> TaskId:
    """Generate a fresh branded task ID."""
    return new_task_id()


def make_agent_id() -> AgentId:
    """Generate a fresh branded agent ID."""
    return new_agent_id()


def make_task(**overrides: Any) -> dict[str, Any]:
    """Create a task dict with sensible defaults.

    All fields can be overridden by passing keyword arguments::

        task = make_task(status=StatusEnum.RUNNING, priority=10)
    """
    defaults: dict[str, Any] = {
        "id": new_task_id(),
        "type": TaskType.IMPLEMENT_FEATURE,
        "agent_type": AgentType.CODER,
        "model_tier": ModelTier.TIER_2,
        "status": StatusEnum.PENDING,
        "priority": 0,
        "dependencies": [],
        "dependents": [],
        "inputs": {},
        "outputs": None,
        "budget": {"max_tokens": 100_000},
        "assigned_agent": None,
        "current_attempt": 0,
        "retry_history": [],
        "verdict": None,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    defaults.update(overrides)
    return defaults


def make_agent_run(**overrides: Any) -> dict[str, Any]:
    """Create an agent run dict with sensible defaults.

    Represents an agent session/run record::

        run = make_agent_run(agent_type=AgentType.REVIEWER)
    """
    defaults: dict[str, Any] = {
        "id": new_agent_id(),
        "agent_type": AgentType.CODER,
        "model_tier": ModelTier.TIER_2,
        "current_task": new_task_id(),
        "status": StatusEnum.RUNNING,
        "tokens_consumed": 0,
        "started_at": utcnow(),
        "last_heartbeat": utcnow(),
        "completed_at": None,
        "config": {},
    }
    defaults.update(overrides)
    return defaults


def make_proposal(**overrides: Any) -> dict[str, Any]:
    """Create a proposal dict with sensible defaults.

    Represents a state mutation proposal::

        proposal = make_proposal(verdict=ProposalVerdict.ACCEPTED)
    """
    defaults: dict[str, Any] = {
        "id": new_proposal_id(),
        "agent_id": new_agent_id(),
        "task_id": new_task_id(),
        "verdict": ProposalVerdict.PENDING,
        "eval_verdict": EvalVerdict.PASS,
        "changes": {},
        "created_at": utcnow(),
        "resolved_at": None,
        "rejection_reason": None,
    }
    defaults.update(overrides)
    return defaults


def make_event(**overrides: Any) -> dict[str, Any]:
    """Create an event dict with sensible defaults.

    Represents an event envelope for the event bus::

        event = make_event(type=EventType.TASK_STARTED)
    """
    defaults: dict[str, Any] = {
        "id": new_event_id(),
        "type": EventType.TASK_CREATED,
        "timestamp": utcnow().isoformat(),
        "correlation_id": None,
        "payload": {},
        "task_id": new_task_id(),
        "agent_id": None,
    }
    defaults.update(overrides)
    return defaults


def make_spec(**overrides: Any) -> dict[str, Any]:
    """Create a spec dict with sensible defaults.

    Represents a parsed task specification::

        spec = make_spec(intent="Implement auth login")
    """
    defaults: dict[str, Any] = {
        "id": f"spec-{new_task_id().removeprefix('task-')}",
        "intent": "Implement a feature",
        "constraints": [],
        "success_criteria": [],
        "file_targets": [],
        "assumptions": [],
        "open_questions": [],
        "created_at": utcnow().isoformat(),
    }
    defaults.update(overrides)
    return defaults


def make_agent_message(**overrides: Any) -> dict[str, Any]:
    """Create an agent message dict with sensible defaults.

    Represents a typed inter-agent message::

        msg = make_agent_message(message_type="task.assigned")
    """
    defaults: dict[str, Any] = {
        "id": f"msg-{new_event_id().removeprefix('evt-')}",
        "sender": new_agent_id(),
        "recipient": None,
        "message_type": "task.assigned",
        "payload": {},
        "correlation_id": None,
        "timestamp": utcnow().isoformat(),
        "reply_to": None,
    }
    defaults.update(overrides)
    return defaults


def make_routing_decision(**overrides: Any) -> dict[str, Any]:
    """Create a routing decision dict with sensible defaults.

    Represents a model routing decision::

        decision = make_routing_decision(selected_tier=ModelTier.TIER_1)
    """
    defaults: dict[str, Any] = {
        "task_id": new_task_id(),
        "selected_tier": ModelTier.TIER_2,
        "model_id": "claude-sonnet-4-20250514",
        "complexity": {"score": 0.5, "factors": {}, "recommended_tier": ModelTier.TIER_2},
        "override_reason": None,
        "timestamp": utcnow().isoformat(),
    }
    defaults.update(overrides)
    return defaults
