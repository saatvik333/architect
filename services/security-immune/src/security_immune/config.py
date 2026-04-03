"""Service-specific configuration for the Security Immune System."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class SecurityImmuneConfig(BaseSettings):
    """Configuration knobs specific to the Security Immune System service."""

    model_config = SettingsConfigDict(env_prefix="SEC_IMMUNE_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8017, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "security-immune"

    # ── Vulnerability database ───────────────────────────────────────
    vuln_db_url: str = "https://osv.dev/v1"

    # ── License allow-list ───────────────────────────────────────────
    allowed_licenses: list[str] = Field(
        default=[
            "MIT",
            "Apache-2.0",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "ISC",
            "PSF-2.0",
        ]
    )

    # ── Code scanning ────────────────────────────────────────────────
    block_on_critical_vuln: bool = True
    max_code_size_kb: int = Field(default=500, ge=1)

    blocked_patterns: list[str] = Field(
        default=[
            "eval(",
            "exec(",  # nosec B102 # pattern string for detection, not execution
            "os.system(",
            "__import__(",
            "subprocess.call(",
            "subprocess.Popen(",
        ]
    )

    secrets_patterns: list[str] = Field(
        default=[
            r"(?i)(?:api[_-]?key|apikey)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{20,}['\"]",
            r"ghp_[a-zA-Z0-9]{36}",
            r"github_pat_[a-zA-Z0-9_]{22,}",
            r"sk-ant-[a-zA-Z0-9\-]{40,}",
            r"sk-[a-zA-Z0-9]{48,}",
            r"(?i)(?:secret|password|token)\s*[:=]\s*['\"][^\s'\"]{8,}['\"]",
            r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
            r"AKIA[0-9A-Z]{16}",
        ]
    )

    # ── Sandbox / runtime monitoring ─────────────────────────────────
    sandbox_url: str = "http://localhost:8007"
    scan_timeout_seconds: int = Field(default=120, ge=1)

    # ── Gate mode ────────────────────────────────────────────────────
    gate_mode: str = Field(default="enforce", pattern=r"^(enforce|audit)$")
