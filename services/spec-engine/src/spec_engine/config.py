"""Service-specific configuration for the Spec Engine."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class SpecEngineConfig(BaseSettings):
    """Configuration knobs specific to the Spec Engine service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    service-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="SPEC_ENGINE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Spec Engine-specific settings ─────────────────────────────────
    max_clarification_rounds: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum rounds of clarification before forcing a best-effort spec.",
    )
    temporal_task_queue: str = "spec-engine"
    host: str = "0.0.0.0"
    port: int = Field(default=8010, ge=1, le=65535)
    log_level: str = "INFO"
