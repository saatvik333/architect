"""Temporal worker entry point for the Failure Taxonomy service."""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner
from failure_taxonomy.temporal.activities import FailureTaxonomyActivities
from failure_taxonomy.temporal.workflows import (
    FailureClassificationWorkflow,
    PostMortemWorkflow,
    SimulationTrainingWorkflow,
)

logger = get_logger(component="failure_taxonomy.temporal.worker")


async def run_worker(
    config: FailureTaxonomyConfig | None = None,
    classifier: FailureClassifier | None = None,
    post_mortem_analyzer: PostMortemAnalyzer | None = None,
    simulation_runner: SimulationRunner | None = None,
    session_factory: Any | None = None,
) -> None:
    """Connect to Temporal and start the failure taxonomy worker.

    When called from :func:`main` (standalone mode), fresh instances are
    created. When called from the FastAPI lifespan, the *shared* singletons
    are passed in so that Temporal activities and the REST API see the same
    state.
    """
    if config is None:
        config = FailureTaxonomyConfig()
    setup_logging(log_level=config.log_level)

    if classifier is None:
        classifier = FailureClassifier(config)
    if post_mortem_analyzer is None:
        post_mortem_analyzer = PostMortemAnalyzer()
    if simulation_runner is None:
        simulation_runner = SimulationRunner()

    logger.info(
        "connecting to temporal",
        target=config.architect.temporal.target,
        namespace=config.architect.temporal.namespace,
        task_queue=config.temporal_task_queue,
    )

    client = await Client.connect(
        config.architect.temporal.target,
        namespace=config.architect.temporal.namespace,
    )

    activities = FailureTaxonomyActivities(
        classifier=classifier,
        post_mortem_analyzer=post_mortem_analyzer,
        simulation_runner=simulation_runner,
        session_factory=session_factory,
    )

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        activities=[
            activities.classify_failure,
            activities.run_post_mortem,
            activities.run_simulation,
            activities.get_failure_stats,
        ],
        workflows=[
            FailureClassificationWorkflow,
            PostMortemWorkflow,
            SimulationTrainingWorkflow,
        ],
    )

    logger.info("failure-taxonomy worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m failure_taxonomy.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
