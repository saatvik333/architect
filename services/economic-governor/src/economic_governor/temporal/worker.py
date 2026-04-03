"""Temporal worker entry point for the Economic Governor."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.temporal.activities import BudgetActivities
from economic_governor.temporal.workflows import (
    BudgetAllocationWorkflow,
    BudgetMonitoringWorkflow,
)

logger = get_logger(component="economic_governor.temporal.worker")


async def run_worker(
    config: EconomicGovernorConfig | None = None,
    budget_tracker: BudgetTracker | None = None,
    efficiency_scorer: EfficiencyScorer | None = None,
) -> None:
    """Connect to Temporal and start the economic governor worker.

    When called from :func:`main` (standalone mode), fresh instances are
    created.  When called from the FastAPI lifespan, the *shared* singletons
    are passed in so that Temporal activities and the REST API see the same
    state.
    """
    if config is None:
        config = EconomicGovernorConfig()
    setup_logging(log_level=config.log_level)

    if budget_tracker is None:
        budget_tracker = BudgetTracker(config)
    if efficiency_scorer is None:
        efficiency_scorer = EfficiencyScorer()

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

    budget_activities = BudgetActivities(budget_tracker, efficiency_scorer)

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        activities=[
            budget_activities.get_budget_status,
            budget_activities.check_budget_for_task,
            budget_activities.record_consumption,
            budget_activities.compute_efficiency_scores,
            budget_activities.enforce_budget,
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
