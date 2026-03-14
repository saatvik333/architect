"""Temporal worker entry point for the Multi-Model Router."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.temporal.activities import route_task

logger = get_logger(component="multi_model_router.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the multi-model router worker."""
    config = MultiModelRouterConfig()
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
        activities=[route_task],
    )

    logger.info("multi-model router worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m multi_model_router.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
