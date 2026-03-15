"""Temporal worker registration for Codebase Comprehension activities."""

from __future__ import annotations

import structlog

from codebase_comprehension.temporal.activities import index_codebase

logger = structlog.get_logger()

TASK_QUEUE = "codebase-comprehension"

ACTIVITIES = [
    index_codebase,
]


async def run_worker(temporal_address: str = "localhost:7233") -> None:
    """Start a Temporal worker for the codebase-comprehension task queue.

    Requires the ``temporalio`` package to be installed.
    """
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        logger.error(
            "temporalio_not_installed",
            msg="Install temporalio to run the Temporal worker.",
        )
        return

    client = await Client.connect(temporal_address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        activities=ACTIVITIES,
    )
    logger.info("temporal_worker_started", task_queue=TASK_QUEUE)
    await worker.run()
