"""Temporal worker entry point for the Coding Agent."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from architect_llm.client import LLMClient
from architect_sandbox_client.client import SandboxClient
from coding_agent.config import CodingAgentConfig
from coding_agent.temporal.activities import CodingAgentActivities
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

    # Instantiate shared dependencies for activity methods.
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.default_model_id,
    )
    sandbox_client = SandboxClient(base_url=config.sandbox_base_url)

    activities = CodingAgentActivities(
        llm_client=llm_client,
        sandbox_client=sandbox_client,
        config=config,
    )

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        workflows=[CodingAgentWorkflow],
        activities=[
            activities.plan_task,
            activities.generate_code,
            activities.execute_in_sandbox,
            activities.commit_code,
            activities.update_world_state,
        ],
    )

    logger.info("coding agent worker started", task_queue=config.temporal_task_queue)
    try:
        await worker.run()
    finally:
        await llm_client.close()
        await sandbox_client.close()


def main() -> None:
    """CLI entry point for ``python -m coding_agent.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
