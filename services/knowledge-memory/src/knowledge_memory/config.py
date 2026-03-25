"""Service-specific configuration for the Knowledge & Memory system."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class KnowledgeMemoryConfig(BaseSettings):
    """Configuration knobs specific to the Knowledge & Memory service."""

    model_config = SettingsConfigDict(env_prefix="KM_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8014, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "knowledge-memory"

    # ── Embedding settings ───────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = Field(default=384, ge=1)

    # ── Compression pipeline ─────────────────────────────────────────
    min_observations_for_pattern: int = Field(default=5, ge=1)
    min_patterns_for_heuristic: int = Field(default=3, ge=1)
    compression_batch_size: int = Field(default=100, ge=1)

    # ── Working memory ───────────────────────────────────────────────
    working_memory_ttl_seconds: int = Field(default=3600, ge=60)
    max_working_memory_entries: int = Field(default=1000, ge=1)

    # ── External connectivity ────────────────────────────────────────
    nats_url: str = "nats://localhost:4222"
    max_doc_fetch_size_kb: int = Field(default=500, ge=1)
