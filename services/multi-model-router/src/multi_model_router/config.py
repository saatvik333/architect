"""Service-specific configuration for the Multi-Model Router."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class MultiModelRouterConfig(BaseSettings):
    """Configuration knobs specific to the Multi-Model Router service."""

    model_config = SettingsConfigDict(env_prefix="ROUTER_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Routing thresholds ───────────────────────────────────────────
    tier_1_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Complexity score above which tasks route to Tier 1 (Opus).",
    )
    tier_2_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Complexity score above which tasks route to Tier 2 (Sonnet).",
    )

    # ── Escalation settings ──────────────────────────────────────────
    max_tier_failures: int = Field(
        default=2,
        ge=1,
        description="Failures at a single tier before escalation.",
    )
    max_total_failures: int = Field(
        default=5,
        ge=1,
        description="Total failures before requiring human intervention.",
    )

    # ── Service settings ─────────────────────────────────────────────
    temporal_task_queue: str = "multi-model-router"
    host: str = "0.0.0.0"
    port: int = Field(default=8011, ge=1, le=65535)
    log_level: str = "INFO"
