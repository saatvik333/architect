"""Pydantic domain models for the World State Ledger."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import (
    BuildResult,
    EnvironmentName,
    HealthStatus,
    LintStatus,
    ProposalVerdict,
    StatusEnum,
)
from architect_common.types import (
    AgentId,
    ArchitectBase,
    CommitHash,
    LedgerVersion,
    MutableBase,
    ProposalId,
    SHA256Hash,
    TaskId,
    new_proposal_id,
    utcnow,
)

# ── Sub-state models (frozen) ────────────────────────────────────────


class SpecState(ArchitectBase):
    """Tracks the current project specification hash."""

    spec_version: SHA256Hash


class RepoState(ArchitectBase):
    """Tracks the repository state — latest commit, topology, manifest."""

    commit_hash: CommitHash
    branch_topology: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of branch name to tip commit hash.",
    )
    file_manifest: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file path to content SHA-256.",
    )
    dependency_lock_hash: SHA256Hash | None = None


class TestResult(ArchitectBase):
    """Summary of a single test suite run."""

    suite: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0


class BuildState(ArchitectBase):
    """Tracks build / CI state."""

    last_build: BuildResult | None = None
    test_results: list[TestResult] = Field(default_factory=list)
    coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    lint_status: LintStatus = LintStatus.CLEAN


class EnvironmentInfo(ArchitectBase):
    """Describes a single deployment environment."""

    name: EnvironmentName
    status: HealthStatus = HealthStatus.UNKNOWN
    deployed_version: str | None = None


class InfraState(ArchitectBase):
    """Tracks infrastructure / deployment environments."""

    environments: list[EnvironmentInfo] = Field(default_factory=list)


class ActiveAgent(ArchitectBase):
    """Summary of a currently active agent."""

    agent_id: AgentId
    task_id: TaskId
    status: StatusEnum = StatusEnum.RUNNING


class AgentState(ArchitectBase):
    """Tracks agent fleet state."""

    active_agents: list[ActiveAgent] = Field(default_factory=list)
    completed_task_ids: list[TaskId] = Field(default_factory=list)
    blocked_task_ids: list[TaskId] = Field(default_factory=list)


class BudgetState(ArchitectBase):
    """Tracks token budget consumption."""

    allocated_tokens: int = 0
    consumed_tokens: int = 0
    remaining_tokens: int = 0
    burn_rate: float = Field(
        default=0.0,
        ge=0.0,
        description="Tokens per minute average.",
    )


# ── Top-level world state (mutable accumulator) ─────────────────────


class WorldState(MutableBase):
    """Full world state snapshot — the single source of truth."""

    version: LedgerVersion = LedgerVersion(0)
    updated_at: datetime = Field(default_factory=utcnow)

    spec: SpecState | None = None
    repo: RepoState | None = None
    build: BuildState = Field(default_factory=BuildState)
    infra: InfraState = Field(default_factory=InfraState)
    agents: AgentState = Field(default_factory=AgentState)
    budget: BudgetState = Field(default_factory=BudgetState)


# ── Mutation / Proposal models ──────────────────────────────────────


class StateMutation(ArchitectBase):
    """A single field-level mutation within a proposal.

    ``path`` is a dot-separated JSON path (e.g. ``"budget.consumed_tokens"``).
    ``old_value`` must match the current state for optimistic concurrency.
    """

    path: str
    old_value: object = None
    new_value: object = None


class Proposal(ArchitectBase):
    """A state mutation proposal submitted by an agent."""

    id: ProposalId = Field(default_factory=new_proposal_id)
    agent_id: AgentId
    task_id: TaskId
    mutations: list[StateMutation] = Field(default_factory=list)
    rationale: str = ""
    verdict: ProposalVerdict = ProposalVerdict.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    verdict_at: datetime | None = None
