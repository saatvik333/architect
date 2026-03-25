"""Temporal worker entry point for the Economic Governor."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from economic_governor.config import EconomicGovernorConfig
from economic_governor.temporal.activities import (
    check_budget_for_task,
    compute_efficiency_scores,
    enforce_budget,
    get_budget_status,
    record_consumption,
)
from economic_governor.temporal.workflows import (
    BudgetAllocationWorkflow,
    BudgetMonitoringWorkflow,
)

logger = get_logger(component="economic_governor.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the economic governor worker."""
    config = EconomicGovernorConfig()
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
        activities=[
            get_budget_status,
            check_budget_for_task,
            record_consumption,
            compute_efficiency_scores,
            enforce_budget,
        ],
        workflows=[
            BudgetMonitoringWorkflow,
            BudgetAllocationWorkflow,
        ],
    )

    logger.info("economic-governor worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m economic_governor.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
