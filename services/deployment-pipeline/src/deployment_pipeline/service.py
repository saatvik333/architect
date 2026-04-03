"""FastAPI application factory for the Deployment Pipeline service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_events.publisher import EventPublisher
from architect_events.subscriber import EventSubscriber
from architect_observability import init_observability, shutdown_observability
from deployment_pipeline.api.dependencies import cleanup, get_config, set_pipeline_manager
from deployment_pipeline.api.routes import router
from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.event_handlers import DeploymentEventHandler
from deployment_pipeline.pipeline_manager import PipelineManager
from deployment_pipeline.temporal.activities import DeploymentActivities
from deployment_pipeline.temporal.worker import run_worker

logger = get_logger(component="deployment_pipeline.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Deployment Pipeline."""
    import time

    app.state.started_at = time.monotonic()
    config: DeploymentPipelineConfig = app.state.config

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()

    # ── Core components ──────────────────────────────────────────────
    activities = DeploymentActivities(
        sandbox_base_url=config.sandbox_base_url,
        evaluation_engine_url=config.evaluation_engine_url,
        human_interface_url=config.human_interface_url,
        event_publisher=event_publisher,
    )

    pipeline_manager = PipelineManager(config=config)
    set_pipeline_manager(pipeline_manager)

    # ── Event subscriptions ──────────────────────────────────────────
    event_handler = DeploymentEventHandler(pipeline_manager)

    subscriber = EventSubscriber(
        redis_url=config.architect.redis.url,
        group="deployment-pipeline",
        consumer="deploy-1",
    )
    subscriber.on(EventType.EVAL_COMPLETED, event_handler.handle_eval_completed)

    try:
        await subscriber.start([EventType.EVAL_COMPLETED])
        logger.info("event subscriber started")
    except Exception:
        logger.warning("event subscriber failed to start — running without it", exc_info=True)

    # ── Temporal worker ──────────────────────────────────────────────
    worker_task: asyncio.Task[None] | None = None
    try:
        worker_task = asyncio.create_task(run_worker(config=config, activities_instance=activities))
        logger.info("temporal worker started as background task")
    except Exception:
        logger.warning("temporal worker failed to start — running without it", exc_info=True)

    logger.info("deployment-pipeline service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    shutdown_observability(app)

    if worker_task is not None:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task

    await subscriber.stop()
    await event_publisher.close()
    await cleanup()

    logger.info("deployment-pipeline service stopped")


def create_app(config: DeploymentPipelineConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = get_config()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="ARCHITECT Deployment Pipeline",
        description="Automated canary deployment with progressive rollout, health monitoring, and rollback.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)
    init_observability(app, "deployment-pipeline")

    return app


def main() -> None:
    """CLI entry point: ``python -m deployment_pipeline.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "deployment_pipeline.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
