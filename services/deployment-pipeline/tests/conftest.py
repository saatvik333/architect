"""Shared pytest fixtures for deployment-pipeline tests."""

from __future__ import annotations

import os

# Ensure required env vars are set for tests that import ArchitectConfig.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock, MagicMock

import pytest

from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.pipeline_manager import PipelineManager
from deployment_pipeline.temporal.activities import DeploymentActivities


@pytest.fixture
def config() -> DeploymentPipelineConfig:
    """Return the default service configuration."""
    return DeploymentPipelineConfig()


@pytest.fixture
def mock_temporal_client() -> AsyncMock:
    """Return a mock Temporal client."""
    client = AsyncMock()
    client.start_workflow = AsyncMock(return_value=MagicMock())
    mock_handle = AsyncMock()
    mock_handle.signal = AsyncMock()
    mock_handle.cancel = AsyncMock()
    client.get_workflow_handle = MagicMock(return_value=mock_handle)
    return client


@pytest.fixture
def pipeline_manager(
    config: DeploymentPipelineConfig,
    mock_temporal_client: AsyncMock,
) -> PipelineManager:
    """Return a PipelineManager with a mock Temporal client."""
    return PipelineManager(config=config, temporal_client=mock_temporal_client)


@pytest.fixture
def pipeline_manager_no_temporal(
    config: DeploymentPipelineConfig,
) -> PipelineManager:
    """Return a PipelineManager without a Temporal client."""
    return PipelineManager(config=config)


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """Return a mock EventPublisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher


@pytest.fixture
def activities(mock_publisher: AsyncMock) -> DeploymentActivities:
    """Return DeploymentActivities with a mock event publisher."""
    return DeploymentActivities(
        sandbox_base_url="http://localhost:8007",
        evaluation_engine_url="http://localhost:8008",
        human_interface_url="http://localhost:8016",
        event_publisher=mock_publisher,
    )
