"""Shared pytest fixtures for economic-governor tests."""

from __future__ import annotations

import os

# Ensure required env vars are set for tests that import ArchitectConfig.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock

import pytest

from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer
from economic_governor.spin_detector import SpinDetector


@pytest.fixture
def config() -> EconomicGovernorConfig:
    """Return the default service configuration."""
    return EconomicGovernorConfig()


@pytest.fixture
def budget_tracker(config: EconomicGovernorConfig) -> BudgetTracker:
    """Return a fresh BudgetTracker."""
    return BudgetTracker(config)


@pytest.fixture
def spin_detector(config: EconomicGovernorConfig) -> SpinDetector:
    """Return a fresh SpinDetector."""
    return SpinDetector(config)


@pytest.fixture
def efficiency_scorer() -> EfficiencyScorer:
    """Return a fresh EfficiencyScorer."""
    return EfficiencyScorer()


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """Return a mock EventPublisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher


@pytest.fixture
def enforcer(config: EconomicGovernorConfig, mock_publisher: AsyncMock) -> Enforcer:
    """Return an Enforcer wired with a mock publisher."""
    return Enforcer(config, mock_publisher)
