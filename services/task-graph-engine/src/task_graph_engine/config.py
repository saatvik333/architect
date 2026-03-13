"""Configuration for the Task Graph Engine service."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import (
    ClaudeConfig,
    PostgresConfig,
    RedisConfig,
    TemporalConfig,
)


class TaskGraphEngineConfig(BaseSettings):
    """Service-level configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TASK_GRAPH_ENGINE_",
        env_nested_delimiter="__",
    )

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)

    host: str = "0.0.0.0"
    port: int = Field(default=8003, ge=1, le=65535)
    log_level: str = "INFO"

    # Scheduling tunables
    max_concurrent_tasks: int = Field(default=10, ge=1)
    default_max_retries: int = Field(default=3, ge=0, le=10)
    default_task_timeout_minutes: int = Field(default=30, ge=1, le=120)
    default_task_max_tokens: int = Field(default=100_000, ge=1000)
