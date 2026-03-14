"""Temporal worker entry point for the Spec Engine."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from spec_engine.config import SpecEngineConfig
from spec_engine.temporal.activities import parse_spec, validate_spec
from spec_engine.temporal.workflows import SpecificationWorkflow

logger = get_logger(component="spec_engine.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the spec engine worker."""
    config = SpecEngineConfig()
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
        workflows=[SpecificationWorkflow],
        activities=[parse_spec, validate_spec],
    )

    logger.info("spec engine worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m spec_engine.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
