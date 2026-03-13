"""Temporal worker entry point for the Evaluation Engine."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from evaluation_engine.config import EvaluationEngineConfig
from evaluation_engine.temporal.activities import run_evaluation
from evaluation_engine.temporal.workflows import EvaluationWorkflow

logger = get_logger(component="evaluation_engine.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the evaluation worker."""
    config = EvaluationEngineConfig()
    setup_logging(log_level=config.log_level)

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

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        workflows=[EvaluationWorkflow],
        activities=[run_evaluation],
    )

    logger.info("evaluation worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m evaluation_engine.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
