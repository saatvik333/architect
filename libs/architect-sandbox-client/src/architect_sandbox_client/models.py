"""Domain models for sandbox execution requests and results."""

from __future__ import annotations

from pydantic import Field

from architect_common.enums import SandboxStatus
from architect_common.types import AgentId, ArchitectBase, TaskId


class ResourceLimitsSpec(ArchitectBase):
    """Resource constraints applied to a sandbox container."""

    cpu_cores: int = Field(default=2, ge=1, le=8)
    memory_mb: int = Field(default=4096, ge=256, le=16384)
    disk_mb: int = Field(default=10240, ge=1024, le=51200)


class ExecutionRequest(ArchitectBase):
    """Request to execute code inside an isolated sandbox."""

    task_id: TaskId
    agent_id: AgentId
    files: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file path to file content to write into the sandbox",
    )
    commands: list[str] = Field(
        default_factory=list,
        description="Shell commands to execute sequentially",
    )
    environment_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set in the sandbox",
    )
    timeout_seconds: int = Field(default=900, ge=10, le=3600)
    resource_limits: ResourceLimitsSpec | None = None


class CommandResult(ArchitectBase):
    """Result of a single command execution inside the sandbox."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)


class ExecutionResult(ArchitectBase):
    """Aggregate result of a full sandbox execution session."""

    session_id: str
    status: SandboxStatus
    command_results: list[CommandResult] = Field(default_factory=list)
    total_duration_ms: int = Field(ge=0)
    files_modified: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file path to content for files modified during execution",
    )
