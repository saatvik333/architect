"""API Gateway configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewayConfig(BaseSettings):
    """Configuration for the API Gateway, loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="ARCHITECT_GATEWAY_")

    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = 8000

    # Backend service URLs — Phase 1
    task_graph_url: str = "http://localhost:8003"
    world_state_url: str = "http://localhost:8001"
    sandbox_url: str = "http://localhost:8007"
    eval_engine_url: str = "http://localhost:8008"
    coding_agent_url: str = "http://localhost:8009"

    # Backend service URLs — Phase 2
    spec_engine_url: str = "http://localhost:8010"
    multi_model_router_url: str = "http://localhost:8011"
    codebase_comprehension_url: str = "http://localhost:8012"
    agent_comm_bus_url: str = "http://localhost:8013"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Authentication — comma-separated string, split in property
    api_keys_raw: str = ""
    auth_enabled: bool = True

    @property
    def api_keys(self) -> list[str]:
        """Split comma-separated API keys string into a list."""
        if not self.api_keys_raw:
            return []
        return [k.strip() for k in self.api_keys_raw.split(",") if k.strip()]

    # Rate limiting
    rate_limit_per_minute: int = 60

    # Request body size limit (bytes)
    max_request_body_bytes: int = 1_048_576  # 1 MB

    # Environment (controls HSTS — only non-dev)
    environment: str = "dev"
