"""FastAPI dependency injection for the Economic Governor."""

from __future__ import annotations

from functools import lru_cache

from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer


@lru_cache(maxsize=1)
def get_config() -> EconomicGovernorConfig:
    """Return the cached service configuration."""
    return EconomicGovernorConfig()


_budget_tracker: BudgetTracker | None = None
_efficiency_scorer: EfficiencyScorer | None = None
_enforcer: Enforcer | None = None


def get_budget_tracker() -> BudgetTracker:
    """Return the shared :class:`BudgetTracker` instance."""
    global _budget_tracker
    if _budget_tracker is None:
        _budget_tracker = BudgetTracker(config=get_config())
    return _budget_tracker


def set_budget_tracker(tracker: BudgetTracker) -> None:
    """Override the shared budget tracker (used during service startup)."""
    global _budget_tracker
    _budget_tracker = tracker


def get_efficiency_scorer() -> EfficiencyScorer:
    """Return the shared :class:`EfficiencyScorer` instance."""
    global _efficiency_scorer
    if _efficiency_scorer is None:
        _efficiency_scorer = EfficiencyScorer()
    return _efficiency_scorer


def set_efficiency_scorer(scorer: EfficiencyScorer) -> None:
    """Override the shared efficiency scorer (used during service startup)."""
    global _efficiency_scorer
    _efficiency_scorer = scorer


def get_enforcer() -> Enforcer:
    """Return the shared :class:`Enforcer` instance."""
    if _enforcer is None:
        msg = "Enforcer not initialised. Call set_enforcer() during startup."
        raise RuntimeError(msg)
    return _enforcer


def set_enforcer(enforcer: Enforcer) -> None:
    """Override the shared enforcer (used during service startup)."""
    global _enforcer
    _enforcer = enforcer


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _budget_tracker, _efficiency_scorer, _enforcer
    if _enforcer is not None:
        await _enforcer.shutdown()
    _budget_tracker = None
    _efficiency_scorer = None
    _enforcer = None
