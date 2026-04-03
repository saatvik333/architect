"""Temporal worker entry point for the Deployment Pipeline."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.temporal.activities import DeploymentActivities
from deployment_pipeline.temporal.workflows import DeploymentWorkflow

logger = get_logger(component="deployment_pipeline.temporal.worker")


async def run_worker(
    config: DeploymentPipelineConfig | None = None,
    activities_instance: DeploymentActivities | None = None,
) -> None:
    """Connect to Temporal and start the deployment pipeline worker.

    When called from :func:`main` (standalone mode), fresh instances are
    created.  When called from the FastAPI lifespan, the *shared* singletons
    are passed in so that Temporal activities and the REST API operate on the
    same HTTP client pool and event publisher.
    """
    if config is None:
        config = DeploymentPipelineConfig()
    setup_logging(log_level=config.log_level)

    if activities_instance is None:
        activities_instance = DeploymentActivities(
            sandbox_base_url=config.sandbox_base_url,
            evaluation_engine_url=config.evaluation_engine_url,
            human_interface_url=config.human_interface_url,
        )

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
            activities_instance.deploy_to_staging_activity,
            activities_instance.run_smoke_tests_activity,
            activities_instance.request_approval_activity,
            activities_instance.deploy_canary_activity,
            activities_instance.collect_health_metrics_activity,
            activities_instance.collect_baseline_metrics_activity,
            activities_instance.check_rollback_criteria_activity,
            activities_instance.set_traffic_activity,
            activities_instance.rollback_activity,
            activities_instance.run_acceptance_verification_activity,
            activities_instance.publish_deployment_event_activity,
        ],
        workflows=[
            DeploymentWorkflow,
        ],
    )

    logger.info("deployment-pipeline worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m deployment_pipeline.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
