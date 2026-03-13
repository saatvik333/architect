"""Core branded ID types and domain value objects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, NewType

from pydantic import BaseModel, ConfigDict, Field

# ── Branded ID types ──────────────────────────────────────────────
AgentId = NewType("AgentId", str)
TaskId = NewType("TaskId", str)
ProposalId = NewType("ProposalId", str)
EventId = NewType("EventId", str)
LedgerVersion = NewType("LedgerVersion", int)


def _prefixed_uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def new_agent_id() -> AgentId:
    return AgentId(_prefixed_uuid("agent"))


def new_task_id() -> TaskId:
    return TaskId(_prefixed_uuid("task"))


def new_proposal_id() -> ProposalId:
    return ProposalId(_prefixed_uuid("prop"))


def new_event_id() -> EventId:
    return EventId(_prefixed_uuid("evt"))


# ── Common field annotations ─────────────────────────────────────
SHA256Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CommitHash = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]


# ── Timestamp helper ─────────────────────────────────────────────
def utcnow() -> datetime:
    return datetime.now(UTC)


# ── Frozen base for all domain models ────────────────────────────
class ArchitectBase(BaseModel):
    """Immutable-by-default base. All domain models inherit this."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        ser_json_timedelta="float",
        str_strip_whitespace=True,
    )


# ── Mutable base for state containers ───────────────────────────
class MutableBase(BaseModel):
    """Mutable base for accumulator models like WorldState."""

    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_timedelta="float",
        str_strip_whitespace=True,
    )
