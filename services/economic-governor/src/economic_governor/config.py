"""Service-specific configuration for the Economic Governor."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class EconomicGovernorConfig(BaseSettings):
    """Configuration knobs specific to the Economic Governor service."""

    model_config = SettingsConfigDict(env_prefix="ECON_GOV_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Service settings ─────────────────────────────────────────────
    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8015, ge=1, le=65535)
    log_level: str = "INFO"
    temporal_task_queue: str = "economic-governor"

    # ── Budget thresholds ────────────────────────────────────────────
    alert_threshold_pct: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="Budget consumed % that triggers an alert.",
    )
    restrict_threshold_pct: float = Field(
        default=95.0,
        ge=0.0,
        le=100.0,
        description="Budget consumed % that triggers tier restrictions.",
    )
    halt_threshold_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Budget consumed % that triggers a full halt.",
    )

    # ── Phase allocation percentages ─────────────────────────────────
    spec_budget_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    planning_budget_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    implementation_budget_pct: float = Field(default=40.0, ge=0.0, le=100.0)
    testing_budget_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    review_budget_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    debugging_budget_pct: float = Field(default=15.0, ge=0.0, le=100.0)
    contingency_budget_pct: float = Field(default=5.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _check_threshold_ordering(self) -> EconomicGovernorConfig:
        if not (self.alert_threshold_pct <= self.restrict_threshold_pct <= self.halt_threshold_pct):
            msg = (
                f"Budget thresholds must satisfy alert <= restrict <= halt, "
                f"got alert={self.alert_threshold_pct}, "
                f"restrict={self.restrict_threshold_pct}, "
                f"halt={self.halt_threshold_pct}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_phase_budgets_sum_to_100(self) -> EconomicGovernorConfig:
        total = (
            self.spec_budget_pct
            + self.planning_budget_pct
            + self.implementation_budget_pct
            + self.testing_budget_pct
            + self.review_budget_pct
            + self.debugging_budget_pct
            + self.contingency_budget_pct
        )
        if abs(total - 100.0) > 0.01:
            msg = f"Phase budget percentages must sum to 100.0 (±0.01), got {total}"
            raise ValueError(msg)
        return self

    # ── Spin detection ───────────────────────────────────────────────
    spin_max_retries: int = Field(default=3, ge=1)
    spin_check_interval_seconds: int = Field(default=30, ge=1)

    # ── Monitoring ───────────────────────────────────────────────────
    budget_poll_interval_seconds: int = Field(default=10, ge=1)
    efficiency_recalc_interval_seconds: int = Field(default=60, ge=1)
    restrict_max_tier: str = "tier_3"

    # ── Service URLs ─────────────────────────────────────────────────
    router_url: str = "http://localhost:8011"
    wsl_url: str = "http://localhost:8001"
    task_graph_url: str = "http://localhost:8003"
