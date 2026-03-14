"""Shared pytest fixtures for multi-model-router tests."""

from __future__ import annotations

import pytest

from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.escalation import EscalationPolicy
from multi_model_router.router import Router
from multi_model_router.scorer import ComplexityScorer


@pytest.fixture
def scorer() -> ComplexityScorer:
    """Return a fresh ComplexityScorer."""
    return ComplexityScorer()


@pytest.fixture
def config() -> MultiModelRouterConfig:
    """Return the default service configuration."""
    return MultiModelRouterConfig()


@pytest.fixture
def task_router(config: MultiModelRouterConfig) -> Router:
    """Return a Router wired with the default config."""
    return Router(config=config)


@pytest.fixture
def escalation_policy(config: MultiModelRouterConfig) -> EscalationPolicy:
    """Return an EscalationPolicy wired with the default config."""
    return EscalationPolicy(
        max_tier_failures=config.max_tier_failures,
        max_total_failures=config.max_total_failures,
    )
