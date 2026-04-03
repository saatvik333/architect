"""Service-specific configuration for the Failure Taxonomy Engine."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class FailureTaxonomyConfig(BaseSettings):
    """Configuration knobs specific to the Failure Taxonomy service."""

    model_config = SettingsConfigDict(env_prefix="FAILURE_TAXONOMY_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8019, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "failure-taxonomy"

    # ── Classification settings ─────────────────────────────────────
    classification_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept a rule-based classification without LLM fallback.",
    )
    use_llm_classification: bool = Field(
        default=True,
        description="Whether to use LLM as a fallback for ambiguous classifications.",
    )

    # ── Post-mortem settings ────────────────────────────────────────
    auto_post_mortem: bool = Field(
        default=True,
        description="Automatically trigger post-mortem analysis when failures accumulate.",
    )
    min_failures_for_post_mortem: int = Field(
        default=1,
        ge=1,
        description="Minimum number of unresolved failures before triggering a post-mortem.",
    )

    # ── Simulation training settings ────────────────────────────────
    simulation_enabled: bool = False
    simulation_interval_hours: int = Field(default=24, ge=1)

    # ── Service URLs ─────────────────────────────────────────────────
    evaluation_engine_url: str = "http://localhost:8004"
    knowledge_memory_url: str = "http://localhost:8014"
    economic_governor_url: str = "http://localhost:8015"
