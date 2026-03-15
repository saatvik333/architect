"""Service-specific configuration for the Agent Communication Bus."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class AgentCommBusConfig(BaseSettings):
    """Configuration knobs specific to the Agent Communication Bus service."""

    model_config = SettingsConfigDict(env_prefix="COMM_BUS_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Bus-specific settings ────────────────────────────────────────
    nats_url: str = "nats://localhost:4222"
    stream_name: str = "ARCHITECT"
    max_retries: int = Field(default=3, ge=0)
    request_timeout_seconds: float = Field(default=5.0, ge=1.0)
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8013, ge=1, le=65535)
    log_level: str = "INFO"
