"""Service-specific configuration for the Human Interface."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class HumanInterfaceConfig(BaseSettings):
    """Configuration knobs specific to the Human Interface service."""

    model_config = SettingsConfigDict(env_prefix="HUMAN_INTERFACE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8016, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "human-interface"

    # ── Escalation settings ──────────────────────────────────────────
    default_escalation_expiry_minutes: int = Field(default=60, ge=1)
    auto_resolve_expired: bool = True

    # ── Connectivity ─────────────────────────────────────────────────
    nats_url: str = "nats://localhost:4222"
    ws_heartbeat_interval_seconds: int = Field(default=30, ge=1)

    # ── Authentication ──────────────────────────────────────────────
    ws_token: str | None = Field(
        default=None,
        description="Expected token for WebSocket authentication (env: ARCHITECT_WS_TOKEN).",
        alias="ARCHITECT_WS_TOKEN",
    )

    # ── Service URLs ─────────────────────────────────────────────────
    wsl_url: str = "http://localhost:8001"
    economic_governor_url: str = "http://localhost:8015"
    task_graph_url: str = "http://localhost:8003"
