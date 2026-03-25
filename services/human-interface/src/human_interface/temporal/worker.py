"""Temporal worker entry point for the Human Interface."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from human_interface.config import HumanInterfaceConfig
from human_interface.temporal.activities import (
    create_approval_gate_activity,
    create_escalation_activity,
    expire_escalation_activity,
    fetch_progress_summary_activity,
    resolve_escalation_activity,
)
from human_interface.temporal.workflows import (
    ApprovalGateWorkflow,
    EscalationTimeoutWorkflow,
)

logger = get_logger(component="human_interface.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the human interface worker."""
    config = HumanInterfaceConfig()
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
            create_escalation_activity,
            resolve_escalation_activity,
            expire_escalation_activity,
            create_approval_gate_activity,
            fetch_progress_summary_activity,
        ],
        workflows=[
            EscalationTimeoutWorkflow,
            ApprovalGateWorkflow,
        ],
    )

    logger.info("human-interface worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m human_interface.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
