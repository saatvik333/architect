"""FastAPI dependency injection for the Failure Taxonomy service."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from architect_common.dependencies import ServiceDependency
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner


@lru_cache(maxsize=1)
def get_config() -> FailureTaxonomyConfig:
    """Return the cached service configuration."""
    return FailureTaxonomyConfig()


_classifier = ServiceDependency[FailureClassifier]("FailureClassifier")
_post_mortem_analyzer = ServiceDependency[PostMortemAnalyzer]("PostMortemAnalyzer")
_simulation_runner = ServiceDependency[SimulationRunner]("SimulationRunner")
_session_factory = ServiceDependency[Any]("SessionFactory")

get_classifier = _classifier.get
set_classifier = _classifier.set
get_post_mortem_analyzer = _post_mortem_analyzer.get
set_post_mortem_analyzer = _post_mortem_analyzer.set
get_simulation_runner = _simulation_runner.get
set_simulation_runner = _simulation_runner.set
get_session_factory = _session_factory.get
set_session_factory = _session_factory.set


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _classifier.cleanup()
    await _post_mortem_analyzer.cleanup()
    await _simulation_runner.cleanup()
    await _session_factory.cleanup()
