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

# ── Phase 3: Knowledge & Memory ──────────────────────────────────
KnowledgeId = NewType("KnowledgeId", str)
PatternId = NewType("PatternId", str)
HeuristicId = NewType("HeuristicId", str)

# ── Phase 3: Human Interface ─────────────────────────────────────
EscalationId = NewType("EscalationId", str)
ApprovalGateId = NewType("ApprovalGateId", str)

# ── Phase 4: Security Immune System ─────────────────────────────
SecurityScanId = NewType("SecurityScanId", str)
SecurityFindingId = NewType("SecurityFindingId", str)
SecurityPolicyId = NewType("SecurityPolicyId", str)

# ── Phase 4: Deployment Pipeline ────────────────────────────────
DeploymentId = NewType("DeploymentId", str)

# ── Phase 4: Failure Taxonomy ───────────────────────────────────
FailureRecordId = NewType("FailureRecordId", str)
PostMortemId = NewType("PostMortemId", str)
ImprovementId = NewType("ImprovementId", str)


def _prefixed_uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def new_agent_id() -> AgentId:
    return AgentId(_prefixed_uuid("agent"))


def new_task_id() -> TaskId:
    return TaskId(_prefixed_uuid("task"))


def new_proposal_id() -> ProposalId:
    return ProposalId(_prefixed_uuid("prop"))


def new_event_id() -> EventId:
    return EventId(_prefixed_uuid("evt"))


def new_knowledge_id() -> KnowledgeId:
    return KnowledgeId(_prefixed_uuid("know"))


def new_pattern_id() -> PatternId:
    return PatternId(_prefixed_uuid("pat"))


def new_heuristic_id() -> HeuristicId:
    return HeuristicId(_prefixed_uuid("heur"))


def new_escalation_id() -> EscalationId:
    return EscalationId(_prefixed_uuid("esc"))


def new_approval_gate_id() -> ApprovalGateId:
    return ApprovalGateId(_prefixed_uuid("gate"))


# ── Phase 4 factories ───────────────────────────────────────────
def new_security_scan_id() -> SecurityScanId:
    return SecurityScanId(_prefixed_uuid("scan"))


def new_security_finding_id() -> SecurityFindingId:
    return SecurityFindingId(_prefixed_uuid("sfnd"))


def new_security_policy_id() -> SecurityPolicyId:
    return SecurityPolicyId(_prefixed_uuid("spol"))


def new_deployment_id() -> DeploymentId:
    return DeploymentId(_prefixed_uuid("deploy"))


def new_failure_record_id() -> FailureRecordId:
    return FailureRecordId(_prefixed_uuid("fail"))


def new_post_mortem_id() -> PostMortemId:
    return PostMortemId(_prefixed_uuid("pm"))


def new_improvement_id() -> ImprovementId:
    return ImprovementId(_prefixed_uuid("imp"))


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
