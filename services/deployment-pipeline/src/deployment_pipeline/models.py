"""Domain models for the Deployment Pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from architect_common.enums import (
    DeploymentStage,
    DeploymentStatus,
    RollbackReason,
)
from architect_common.types import (
    ApprovalGateId,
    ArchitectBase,
    DeploymentId,
    MutableBase,
    TaskId,
    utcnow,
)

# ── Immutable value objects ──────────────────────────────────────


class DeploymentArtifact(ArchitectBase):
    """Describes the artifact to be deployed."""

    task_id: TaskId
    artifact_ref: str = Field(description="Container image tag or artifact path.")
    eval_report_summary: str = Field(
        default="",
        description="Summary of the evaluation report that triggered this deployment.",
    )


class HealthMetrics(ArchitectBase):
    """A snapshot of health metrics at a point in time."""

    error_rate: float = Field(ge=0.0, description="Errors per request (0.0-1.0).")
    p50_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    p99_latency_ms: float = Field(ge=0.0)
    request_count: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=utcnow)


class BaselineMetrics(ArchitectBase):
    """Statistical baseline from the existing production deployment."""

    error_rate_mean: float = Field(ge=0.0)
    error_rate_stddev: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)


class RolloutStep(ArchitectBase):
    """A single step in the progressive rollout plan."""

    traffic_pct: int = Field(ge=1, le=100)
    min_duration_seconds: int = Field(ge=0)
    health_check_interval_seconds: int = Field(default=30, ge=5)


class SmokeTestResult(ArchitectBase):
    """Outcome of the smoke test suite."""

    passed: bool
    tests_run: int = Field(ge=0)
    tests_failed: int = Field(ge=0)
    failure_details: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0.0)


class DeploymentPlan(ArchitectBase):
    """Full deployment plan including rollout strategy and thresholds."""

    deployment_id: DeploymentId
    artifact: DeploymentArtifact
    rollout_steps: list[RolloutStep] = Field(
        default_factory=lambda: [
            RolloutStep(traffic_pct=5, min_duration_seconds=300, health_check_interval_seconds=30),
            RolloutStep(traffic_pct=25, min_duration_seconds=300, health_check_interval_seconds=30),
            RolloutStep(traffic_pct=50, min_duration_seconds=300, health_check_interval_seconds=30),
            RolloutStep(
                traffic_pct=100, min_duration_seconds=300, health_check_interval_seconds=30
            ),
        ]
    )
    rollback_error_sigma: float = 2.0
    rollback_latency_multiplier: float = 2.0


# ── Mutable deployment state ────────────────────────────────────


class DeploymentState(MutableBase):
    """Tracks the live state of an in-progress deployment."""

    deployment_id: DeploymentId
    status: DeploymentStatus = DeploymentStatus.PENDING
    current_stage: DeploymentStage | None = None
    current_traffic_pct: int = 0
    baseline: BaselineMetrics | None = None
    health_history: list[HealthMetrics] = Field(default_factory=list)
    smoke_test_result: SmokeTestResult | None = None
    approval_gate_id: ApprovalGateId | None = None
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    rollback_reason: RollbackReason | None = None
    artifact: DeploymentArtifact | None = None
    confidence: float = 0.0
