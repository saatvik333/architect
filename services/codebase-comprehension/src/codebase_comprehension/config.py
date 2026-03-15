"""Service-specific configuration for Codebase Comprehension."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class CodebaseComprehensionConfig(BaseSettings):
    """Configuration knobs specific to the Codebase Comprehension service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    service-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="CODEBASE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # -- Service-specific settings ------------------------------------------
    max_files_per_index: int = Field(
        default=10000,
        ge=1,
        description="Maximum number of files to index in a single directory.",
    )
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8012, ge=1, le=65535)
    log_level: str = "INFO"
