"""Temporal worker entry point for the Knowledge & Memory service."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from knowledge_memory.config import KnowledgeMemoryConfig
from knowledge_memory.temporal.activities import (
    cluster_observations_activity,
    compress_cluster_activity,
    derive_meta_strategies_activity,
    fetch_documentation_activity,
    fetch_uncompressed_observations_activity,
    mine_examples_activity,
    publish_knowledge_update_activity,
    store_knowledge_activity,
    summarize_documentation_activity,
    synthesize_heuristics_activity,
    tag_versions_activity,
)
from knowledge_memory.temporal.workflows import (
    CompressionWorkflow,
    KnowledgeAcquisitionWorkflow,
)

logger = get_logger(component="knowledge_memory.temporal.worker")


async def run_worker() -> None:
    """Connect to Temporal and start the knowledge-memory worker."""
    config = KnowledgeMemoryConfig()
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
        workflows=[
            KnowledgeAcquisitionWorkflow,
            CompressionWorkflow,
        ],
        activities=[
            fetch_documentation_activity,
            summarize_documentation_activity,
            mine_examples_activity,
            tag_versions_activity,
            store_knowledge_activity,
            publish_knowledge_update_activity,
            fetch_uncompressed_observations_activity,
            cluster_observations_activity,
            compress_cluster_activity,
            synthesize_heuristics_activity,
            derive_meta_strategies_activity,
        ],
    )

    logger.info("knowledge-memory worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m knowledge_memory.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
