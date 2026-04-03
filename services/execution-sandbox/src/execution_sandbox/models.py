"""Pydantic models for the Execution Sandbox."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from architect_common.enums import SandboxStatus
from architect_common.types import AgentId, ArchitectBase, MutableBase, TaskId, utcnow


# ── Resource Limits ──────────────────────────────────────────────────
class ResourceLimits(ArchitectBase):
    """Hardware resource caps for a sandbox container."""

    cpu_cores: int = Field(default=2, ge=1, le=8, description="Number of CPU cores allocated.")
    memory_mb: int = Field(default=4096, ge=256, le=16384, description="Memory limit in MiB.")
    disk_mb: int = Field(default=10240, ge=512, le=51200, description="Disk space limit in MiB.")
    timeout_seconds: int = Field(
        default=900, ge=30, le=7200, description="Maximum wall-clock seconds."
    )


# ── Network Policy ───────────────────────────────────────────────────
class NetworkPolicy(ArchitectBase):
    """Network egress rules for a sandbox container."""

    allow_egress: bool = Field(
        default=False, description="Whether the container may make outbound connections."
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "pypi.org",
            "files.pythonhosted.org",
            "registry.npmjs.org",
            "crates.io",
            "static.crates.io",
            "repo.maven.apache.org",
            "rubygems.org",
        ],
        description="Hosts the container is allowed to contact when egress is enabled.",
    )
    blocked_hosts: list[str] = Field(
        default_factory=list,
        description="Explicit deny-list that overrides allowed_hosts.",
    )


# ── Sandbox Spec ─────────────────────────────────────────────────────
class SandboxSpec(ArchitectBase):
    """Full specification for creating a sandbox container."""

    task_id: TaskId
    agent_id: AgentId
    base_image: str = "architect-sandbox:latest"
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    network_policy: NetworkPolicy = Field(default_factory=NetworkPolicy)
    environment_vars: dict[str, str] = Field(default_factory=dict)
    mount_paths: list[str] = Field(default_factory=list)


# ── Audit Log Entry ──────────────────────────────────────────────────
class AuditLogEntry(ArchitectBase):
    """Single command execution recorded in the audit trail."""

    sequence: int = Field(ge=0, description="Monotonically increasing command index.")
    timestamp: datetime = Field(default_factory=utcnow)
    command: str
    exit_code: int
    stdout_truncated: str = Field(default="", description="Stdout (possibly truncated).")
    stderr_truncated: str = Field(default="", description="Stderr (possibly truncated).")
    duration_ms: float = Field(ge=0, description="Command wall-clock duration in milliseconds.")
    working_directory: str = Field(default="/workspace")


# ── Sandbox Session Timestamps ───────────────────────────────────────
class SessionTimestamps(MutableBase):
    """Lifecycle timestamps for a sandbox session."""

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    destroyed_at: datetime | None = None


# ── Resource Usage Snapshot ──────────────────────────────────────────
class ResourceUsage(ArchitectBase):
    """Point-in-time resource consumption reading."""

    cpu_percent: float = Field(default=0.0, ge=0.0)
    memory_used_mb: float = Field(default=0.0, ge=0.0)
    memory_limit_mb: float = Field(default=0.0, ge=0.0)
    disk_used_mb: float = Field(default=0.0, ge=0.0)


# ── Sandbox Session ─────────────────────────────────────────────────
class SandboxSession(MutableBase):
    """Full state of a running or completed sandbox session.

    Uses :class:`MutableBase` because the session accumulates audit log
    entries and transitions through statuses during its lifetime.
    """

    id: str = Field(default_factory=lambda: f"sbx-{uuid.uuid4().hex[:12]}")
    spec: SandboxSpec
    status: SandboxStatus = SandboxStatus.CREATING
    container_id: str | None = None
    executor_type: str = Field(
        default="docker",
        description="Backend that created this session: 'docker' or 'firecracker'.",
    )
    timestamps: SessionTimestamps = Field(default_factory=SessionTimestamps)
    audit_log: list[AuditLogEntry] = Field(default_factory=list)
    exit_code: int | None = None
    resource_usage: ResourceUsage = Field(default_factory=ResourceUsage)
