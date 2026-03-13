"""Pydantic domain models for the Coding Agent."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import AgentType, ModelTier, StatusEnum
from architect_common.types import (
    AgentId,
    ArchitectBase,
    TaskId,
    new_agent_id,
)

# ── Context models ────────────────────────────────────────────────────


class CodebaseContext(ArchitectBase):
    """Snapshot of the relevant codebase state for an agent run."""

    commit_hash: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    file_contents: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file path to file content.",
    )
    dependency_manifest: str = ""
    total_tokens_estimate: int = Field(default=0, ge=0)


class SpecContext(ArchitectBase):
    """The specification (task description) an agent must implement."""

    spec_hash: str = ""
    title: str = ""
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


# ── Output models ─────────────────────────────────────────────────────


class GeneratedFile(ArchitectBase):
    """A single file produced by the coding agent."""

    path: str
    content: str
    is_test: bool = False


class AgentOutput(ArchitectBase):
    """The complete output of a coding agent run."""

    task_id: TaskId
    agent_id: AgentId
    files: list[GeneratedFile] = Field(default_factory=list)
    commit_message: str = ""
    reasoning_summary: str = ""
    tokens_used: int = Field(default=0, ge=0)
    model_id: str = ""


# ── Configuration and run models ──────────────────────────────────────


class AgentConfig(ArchitectBase):
    """Configuration for a specific agent execution."""

    agent_type: AgentType = AgentType.CODER
    model_tier: ModelTier = ModelTier.TIER_2
    model_id: str = "claude-sonnet-4-20250514"
    max_context_tokens: int = Field(default=180_000, ge=1000)
    max_output_tokens: int = Field(default=16_000, ge=100)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    system_prompt: str = ""


class AgentRun(ArchitectBase):
    """Full state of a coding agent run (request + progress + result)."""

    id: AgentId = Field(default_factory=new_agent_id)
    task_id: TaskId
    config: AgentConfig = Field(default_factory=AgentConfig)
    status: StatusEnum = StatusEnum.PENDING
    spec_context: SpecContext = Field(default_factory=SpecContext)
    codebase_context: CodebaseContext = Field(default_factory=CodebaseContext)
    output: AgentOutput | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
