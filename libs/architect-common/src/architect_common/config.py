"""Configuration schema for the ARCHITECT system.

Loaded from environment variables using pydantic-settings.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_PG_")

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "architect"
    user: str = "architect"
    password: SecretStr

    @field_validator("password", mode="before")
    @classmethod
    def _password_must_be_set(cls, v: str | SecretStr) -> str | SecretStr:
        raw = v.get_secret_value() if isinstance(v, SecretStr) else v
        if not raw:
            msg = "ARCHITECT_PG_PASSWORD must be set (use scripts/dev-setup.sh to generate)"
            raise ValueError(msg)
        return v

    pool_size: int = Field(default=3, ge=1)
    max_overflow: int = Field(default=5, ge=0)
    pool_recycle: int = Field(default=3600, ge=0)
    pool_timeout: int = Field(default=30, ge=1)

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:"
            f"{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_REDIS_")

    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0, le=15)
    password: SecretStr = SecretStr("")

    @property
    def url(self) -> str:
        pw = self.password.get_secret_value()
        auth = f":{pw}@" if pw else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class TemporalConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_TEMPORAL_")

    host: str = "localhost"
    port: int = Field(default=7233, ge=1, le=65535)
    namespace: str = "architect"
    task_queue: str = "architect-tasks"

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


class SandboxConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_SANDBOX_")

    base_image: str = "architect-sandbox:latest"
    cpu_cores: int = Field(default=2, ge=1, le=4)
    memory_mb: int = Field(default=4096, ge=256, le=8192)
    disk_mb: int = Field(default=10240, ge=1024, le=20480)
    timeout_minutes: int = Field(default=15, ge=1, le=60)
    docker_socket: str = "/var/run/docker.sock"
    docker_host: str = ""  # e.g. tcp://docker-socket-proxy:2375


class ClaudeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_CLAUDE_")

    api_key: SecretStr = SecretStr("")
    model_id: str = "claude-sonnet-4-20250514"
    max_context_tokens: int = Field(default=180_000, ge=1000)
    max_output_tokens: int = Field(default=16_000, ge=100)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=120, ge=10)


class BudgetConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHITECT_BUDGET_")

    total_tokens: int = Field(default=10_000_000, ge=0)
    warning_threshold_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    hard_stop_threshold_pct: float = Field(default=95.0, ge=0.0, le=100.0)


class ArchitectConfig(BaseSettings):
    """Root configuration aggregating all sub-configs."""

    model_config = SettingsConfigDict(
        env_prefix="ARCHITECT_",
        env_nested_delimiter="__",
    )

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    log_level: str = "INFO"
    environment: str = "dev"
