"""FastAPI dependency injection for the Economic Governor."""

from __future__ import annotations

from functools import lru_cache

from architect_common.dependencies import ServiceDependency
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer


@lru_cache(maxsize=1)
def get_config() -> EconomicGovernorConfig:
    """Return the cached service configuration."""
    return EconomicGovernorConfig()


_budget_tracker = ServiceDependency[BudgetTracker]("BudgetTracker")
_efficiency_scorer = ServiceDependency[EfficiencyScorer]("EfficiencyScorer")
_enforcer = ServiceDependency[Enforcer]("Enforcer")

get_budget_tracker = _budget_tracker.get
set_budget_tracker = _budget_tracker.set
get_efficiency_scorer = _efficiency_scorer.get
set_efficiency_scorer = _efficiency_scorer.set
get_enforcer = _enforcer.get
set_enforcer = _enforcer.set


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _budget_tracker.cleanup()
    await _efficiency_scorer.cleanup()
    await _enforcer.cleanup()
