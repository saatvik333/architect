"""FastAPI dependency injection for the Deployment Pipeline."""

from __future__ import annotations

from functools import lru_cache

from architect_common.dependencies import ServiceDependency
from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.pipeline_manager import PipelineManager


@lru_cache(maxsize=1)
def get_config() -> DeploymentPipelineConfig:
    """Return the cached service configuration."""
    return DeploymentPipelineConfig()


_pipeline_manager = ServiceDependency[PipelineManager]("PipelineManager")

get_pipeline_manager = _pipeline_manager.get
set_pipeline_manager = _pipeline_manager.set


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _pipeline_manager.cleanup()
