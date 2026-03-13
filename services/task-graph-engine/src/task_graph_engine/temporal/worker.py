"""Temporal worker for the Task Graph Engine."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.config import TemporalConfig
from architect_common.logging import get_logger, setup_logging
from task_graph_engine.temporal.activities import (
    check_budget,
    decompose_spec,
    execute_task,
    schedule_next_task,
    update_task_status,
)
from task_graph_engine.temporal.workflows import TASK_QUEUE, TaskOrchestrationWorkflow

logger = get_logger(component="temporal_worker")


async def run_worker(config: TemporalConfig | None = None) -> None:
    """Connect to Temporal and run the task graph engine worker.

    This blocks until interrupted.

    Args:
        config: Temporal connection settings.  Defaults are loaded from
                environment variables via :class:`TemporalConfig`.
    """
    if config is None:
        config = TemporalConfig()

    logger.info(
        "Connecting to Temporal",
        target=config.target,
        namespace=config.namespace,
    )
    client = await Client.connect(config.target, namespace=config.namespace)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TaskOrchestrationWorkflow],
        activities=[
            decompose_spec,
            schedule_next_task,
            update_task_status,
            execute_task,
            check_budget,
        ],
    )

    logger.info("Temporal worker started", task_queue=TASK_QUEUE)
    await worker.run()


def main() -> None:
    """Entry point for ``python -m task_graph_engine.temporal.worker``."""
    setup_logging()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
