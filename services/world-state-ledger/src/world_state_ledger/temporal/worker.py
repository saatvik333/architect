"""Temporal worker setup for the World State Ledger service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from architect_common.logging import get_logger
from world_state_ledger.temporal.activities import WSLActivities

if TYPE_CHECKING:
    from world_state_ledger.config import WorldStateLedgerConfig
    from world_state_ledger.event_log import EventLog
    from world_state_ledger.state_manager import StateManager

logger = get_logger(component="world_state_ledger.temporal.worker")


async def start_temporal_worker(
    config: WorldStateLedgerConfig,
    state_manager: StateManager,
    event_log: EventLog,
) -> Worker:
    """Connect to Temporal and return a running :class:`Worker`.

    The worker registers all WSL activities and begins polling the
    configured task queue.  The caller is responsible for keeping the
    event loop alive (typically via ``worker.run()`` or as a background
    task).
    """
    activities = WSLActivities(state_manager=state_manager, event_log=event_log)

    temporal_cfg = config.architect.temporal
    client = await TemporalClient.connect(temporal_cfg.target, namespace=temporal_cfg.namespace)

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        activities=[
            activities.get_current_state,
            activities.submit_proposal,
            activities.validate_and_commit,
        ],
    )

    logger.info(
        "temporal worker created",
        task_queue=config.temporal_task_queue,
        namespace=temporal_cfg.namespace,
    )
    return worker


async def run_worker(
    config: WorldStateLedgerConfig,
    state_manager: StateManager,
    event_log: EventLog,
) -> None:
    """Convenience entry-point that starts the Temporal worker and blocks."""
    worker = await start_temporal_worker(config, state_manager, event_log)
    logger.info("temporal worker starting")
    await worker.run()
