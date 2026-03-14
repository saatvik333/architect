"""FastAPI dependency injection for the Multi-Model Router."""

from __future__ import annotations

from functools import lru_cache

from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.escalation import EscalationPolicy
from multi_model_router.router import Router
from multi_model_router.scorer import ComplexityScorer


@lru_cache(maxsize=1)
def get_config() -> MultiModelRouterConfig:
    """Return the cached service configuration."""
    return MultiModelRouterConfig()


_scorer: ComplexityScorer | None = None
_router: Router | None = None
_escalation_policy: EscalationPolicy | None = None


def get_scorer() -> ComplexityScorer:
    """Return a shared :class:`ComplexityScorer` instance."""
    global _scorer
    if _scorer is None:
        _scorer = ComplexityScorer()
    return _scorer


def get_router() -> Router:
    """Return a shared :class:`Router` instance."""
    global _router
    if _router is None:
        config = get_config()
        _router = Router(config=config)
    return _router


def get_escalation_policy() -> EscalationPolicy:
    """Return a shared :class:`EscalationPolicy` instance."""
    global _escalation_policy
    if _escalation_policy is None:
        config = get_config()
        _escalation_policy = EscalationPolicy(
            max_tier_failures=config.max_tier_failures,
            max_total_failures=config.max_total_failures,
        )
    return _escalation_policy


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _scorer, _router, _escalation_policy
    _scorer = None
    _router = None
    _escalation_policy = None
