"""Service-specific configuration for the Deployment Pipeline."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class DeploymentPipelineConfig(BaseSettings):
    """Configuration knobs specific to the Deployment Pipeline service."""

    model_config = SettingsConfigDict(env_prefix="DEPLOY_PIPELINE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8018, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "deployment-pipeline"

    # ── Canary / rollout settings ────────────────────────────────────
    canary_traffic_pct: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Initial canary traffic percentage.",
    )
    health_check_duration_seconds: int = Field(
        default=300,
        ge=10,
        description="How long to monitor health at each rollout step.",
    )
    health_check_interval_seconds: int = Field(
        default=30,
        ge=5,
        description="Interval between health metric collections.",
    )

    # ── Rollback criteria ────────────────────────────────────────────
    rollback_error_sigma: float = Field(
        default=2.0,
        gt=0.0,
        description="Number of standard deviations above baseline error rate to trigger rollback.",
    )
    rollback_latency_multiplier: float = Field(
        default=2.0,
        gt=1.0,
        description="Multiplier above baseline p95 latency to trigger rollback.",
    )

    # ── Approval gate ────────────────────────────────────────────────
    auto_approve_confidence_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Minimum evaluation confidence to skip human approval.",
    )
    first_deploy_requires_human: bool = Field(
        default=True,
        description="Whether the first deployment of a project always requires human approval.",
    )
    approval_timeout_minutes: int = Field(
        default=60,
        ge=1,
        description="Minutes to wait for human approval before timing out.",
    )

    # ── Service URLs ─────────────────────────────────────────────────
    evaluation_engine_url: str = "http://localhost:8008"
    human_interface_url: str = "http://localhost:8016"
    sandbox_base_url: str = "http://localhost:8007"
