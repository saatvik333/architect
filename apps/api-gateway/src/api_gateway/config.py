"""API Gateway configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewayConfig(BaseSettings):
    """Configuration for the API Gateway, loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="ARCHITECT_GATEWAY_")

    host: str = "0.0.0.0"
    port: int = 8000

    # Backend service URLs
    task_graph_url: str = "http://localhost:8001"
    world_state_url: str = "http://localhost:8002"
    sandbox_url: str = "http://localhost:8003"
    eval_engine_url: str = "http://localhost:8004"
    coding_agent_url: str = "http://localhost:8005"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Rate limiting
    rate_limit_per_minute: int = 60
