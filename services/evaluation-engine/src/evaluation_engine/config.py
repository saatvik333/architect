"""Service-specific configuration for the Evaluation Engine."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class EvaluationEngineConfig(BaseSettings):
    """Configuration knobs specific to the Evaluation Engine service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    evaluation-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="EVAL_ENGINE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Evaluation-specific settings ─────────────────────────────────
    enabled_layers: list[str] = Field(
        default_factory=lambda: [
            "compilation",
            "unit_tests",
            "integration_tests",
            "architecture",
            "regression",
        ],
        description="Which eval layers are active.",
    )
    max_layer_timeout_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum wall-clock seconds for a single evaluation layer.",
    )
    fail_fast: bool = Field(
        default=True,
        description="Stop evaluating further layers on FAIL_HARD.",
    )
    temporal_task_queue: str = Field(
        default="evaluation-engine",
        description="Temporal task queue name for this service.",
    )
    sandbox_base_url: str = Field(
        default="http://localhost:8002",
        description="Base URL of the Execution Sandbox service.",
    )
    host: str = "0.0.0.0"
    port: int = Field(default=8008, ge=1, le=65535)
    log_level: str = "INFO"
