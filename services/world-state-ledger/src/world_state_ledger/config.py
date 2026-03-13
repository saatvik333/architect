"""Service-specific configuration for the World State Ledger."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class WorldStateLedgerConfig(BaseSettings):
    """Configuration knobs specific to the World State Ledger service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    ledger-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="WSL_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Ledger-specific settings ─────────────────────────────────────
    cache_ttl_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        description="TTL for the current-state Redis cache entry.",
    )
    max_mutations_per_proposal: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of mutations allowed in a single proposal.",
    )
    snapshot_retention_count: int = Field(
        default=1000,
        ge=10,
        description="Number of historical ledger snapshots to retain before pruning.",
    )
    temporal_task_queue: str = Field(
        default="world-state-ledger",
        description="Temporal task queue name for this service.",
    )
    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
