"""Temporal activity definitions for the Evaluation Engine."""

from __future__ import annotations

from temporalio import activity

from architect_common.logging import get_logger
from architect_common.types import TaskId
from architect_events.publisher import EventPublisher
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.config import EvaluationEngineConfig
from evaluation_engine.evaluator import Evaluator

logger = get_logger(component="evaluation_engine.temporal.activities")


@activity.defn
async def run_evaluation(task_id: str, sandbox_session_id: str) -> dict:
    """Run the full evaluation pipeline for a task.

    This activity is designed to be executed by a Temporal worker.  It
    instantiates the :class:`Evaluator` with default layers and returns
    the evaluation report as a serialisable dict.

    Args:
        task_id: Branded task identifier.
        sandbox_session_id: The sandbox session containing code to evaluate.

    Returns:
        A dict representation of the :class:`EvaluationReport`.
    """
    activity.logger.info(
        "run_evaluation activity started",
        extra={"task_id": task_id, "sandbox_session_id": sandbox_session_id},
    )

    config = EvaluationEngineConfig()
    sandbox_client = SandboxClient(base_url=config.sandbox_base_url)
    event_publisher = EventPublisher(redis_url=config.architect.redis.url)

    try:
        await event_publisher.connect()

        evaluator = Evaluator(
            sandbox_client=sandbox_client,
            event_publisher=event_publisher,
            fail_fast=config.fail_fast,
        )

        report = await evaluator.evaluate(
            task_id=TaskId(task_id),
            sandbox_session_id=sandbox_session_id,
        )

        return report.model_dump(mode="json")
    finally:
        await event_publisher.close()
        await sandbox_client.close()
