"""Service-specific configuration for the Coding Agent."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class CodingAgentConfig(BaseSettings):
    """Configuration knobs specific to the Coding Agent service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    agent-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="CODING_AGENT_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Agent-specific settings ──────────────────────────────────────
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum code-generation retry attempts on test failure.",
    )
    default_model_id: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default Claude model for code generation.",
    )
    default_max_context_tokens: int = Field(
        default=180_000,
        ge=1000,
        description="Default max context window for agent LLM calls.",
    )
    default_max_output_tokens: int = Field(
        default=16_000,
        ge=100,
        description="Default max output tokens per LLM call.",
    )
    default_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Default sampling temperature for code generation.",
    )
    sandbox_base_url: str = Field(
        default="http://localhost:8002",
        description="Base URL of the Execution Sandbox service.",
    )
    temporal_task_queue: str = Field(
        default="coding-agent",
        description="Temporal task queue name for this service.",
    )
    host: str = "0.0.0.0"
    port: int = Field(default=8009, ge=1, le=65535)
    log_level: str = "INFO"
