"""Shared pytest fixtures for failure-taxonomy tests."""

from __future__ import annotations

import os

# Ensure required env vars are set for tests that import ArchitectConfig.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock, MagicMock

import pytest

from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner


@pytest.fixture
def config() -> FailureTaxonomyConfig:
    """Return the default service configuration."""
    return FailureTaxonomyConfig()


@pytest.fixture
def config_no_llm() -> FailureTaxonomyConfig:
    """Return a config with LLM classification disabled."""
    return FailureTaxonomyConfig(use_llm_classification=False)


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Return a mock LLMClient."""
    client = AsyncMock()
    client.generate = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def classifier(config_no_llm: FailureTaxonomyConfig) -> FailureClassifier:
    """Return a FailureClassifier with LLM disabled."""
    return FailureClassifier(config_no_llm, llm_client=None)


@pytest.fixture
def classifier_with_llm(
    config: FailureTaxonomyConfig, mock_llm_client: AsyncMock
) -> FailureClassifier:
    """Return a FailureClassifier with a mock LLM client."""
    return FailureClassifier(config, llm_client=mock_llm_client)


@pytest.fixture
def post_mortem_analyzer() -> PostMortemAnalyzer:
    """Return a PostMortemAnalyzer without LLM."""
    return PostMortemAnalyzer(llm_client=None)


@pytest.fixture
def post_mortem_analyzer_with_llm(mock_llm_client: AsyncMock) -> PostMortemAnalyzer:
    """Return a PostMortemAnalyzer with a mock LLM client."""
    return PostMortemAnalyzer(llm_client=mock_llm_client)


@pytest.fixture
def simulation_runner() -> SimulationRunner:
    """Return a SimulationRunner."""
    return SimulationRunner()


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """Return a mock EventPublisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher


@pytest.fixture
def mock_session_factory() -> MagicMock:
    """Return a mock async session factory."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    return factory
