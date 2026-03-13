"""Temporal worker entry point for the Coding Agent."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from coding_agent.config import CodingAgentConfig
from coding_agent.temporal.activities import (
    execute_in_sandbox,
    generate_code,
    plan_task,
)
from coding_agent.temporal.workflows import CodingAgentWorkflow

logger = get_logger(component="coding_agent.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the coding agent worker."""
    config = CodingAgentConfig()
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
        workflows=[CodingAgentWorkflow],
        activities=[plan_task, generate_code, execute_in_sandbox],
    )

    logger.info("coding agent worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m coding_agent.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
