"""FastAPI application factory for the Failure Taxonomy service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_db.engine import create_engine, create_session_factory
from architect_events.publisher import EventPublisher
from architect_events.subscriber import EventSubscriber
from architect_llm.client import LLMClient
from architect_observability import init_observability, shutdown_observability
from failure_taxonomy.api.dependencies import (
    cleanup,
    get_config,
    set_classifier,
    set_post_mortem_analyzer,
    set_session_factory,
    set_simulation_runner,
)
from failure_taxonomy.api.routes import router
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.event_handlers import FailureTaxonomyEventHandlers
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner
from failure_taxonomy.temporal.worker import run_worker

logger = get_logger(component="failure_taxonomy.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Failure Taxonomy service."""
    import time

    app.state.started_at = time.monotonic()
    config: FailureTaxonomyConfig = app.state.config

    # ── Database session factory ─────────────────────────────────────
    db_engine = create_engine(config.architect.postgres.dsn)
    session_factory = create_session_factory(db_engine)

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()

    # ── LLM client (optional) ────────────────────────────────────────
    llm_client: LLMClient | None = None
    api_key = config.architect.claude.api_key.get_secret_value()
    if api_key and config.use_llm_classification:
        llm_client = LLMClient(
            api_key=api_key,
            default_model=config.architect.claude.model_id,
            max_retries=config.architect.claude.max_retries,
            timeout=config.architect.claude.timeout_seconds,
        )

    # ── Core components ──────────────────────────────────────────────
    classifier = FailureClassifier(config, llm_client=llm_client)
    post_mortem_analyzer = PostMortemAnalyzer(llm_client=llm_client)
    simulation_runner = SimulationRunner()

    # Wire into DI
    set_classifier(classifier)
    set_post_mortem_analyzer(post_mortem_analyzer)
    set_simulation_runner(simulation_runner)
    set_session_factory(session_factory)

    # ── Event handlers ───────────────────────────────────────────────
    handlers = FailureTaxonomyEventHandlers(
        config=config,
        classifier=classifier,
        event_publisher=event_publisher,
        session_factory=session_factory,
    )

    subscriber = EventSubscriber(
        redis_url=config.architect.redis.url,
        group="failure-taxonomy",
        consumer="ft-1",
    )
    subscriber.on(EventType.EVAL_COMPLETED, handlers.handle_eval_completed)
    subscriber.on(EventType.TASK_FAILED, handlers.handle_task_failed)
    subscriber.on(EventType.DEPLOYMENT_ROLLED_BACK, handlers.handle_deployment_rolled_back)

    event_types = [
        EventType.EVAL_COMPLETED,
        EventType.TASK_FAILED,
        EventType.DEPLOYMENT_ROLLED_BACK,
    ]

    try:
        await subscriber.start(event_types)
        logger.info("event subscriber started")
    except Exception:
        logger.warning("event subscriber failed to start — running without it", exc_info=True)

    # ── Temporal worker (shares classifier / analyzer) ───────────────
    worker_task: asyncio.Task[None] | None = None
    try:
        worker_task = asyncio.create_task(
            run_worker(
                config=config,
                classifier=classifier,
                post_mortem_analyzer=post_mortem_analyzer,
                simulation_runner=simulation_runner,
                session_factory=session_factory,
            )
        )
        logger.info("temporal worker started as background task")
    except Exception:
        logger.warning("temporal worker failed to start — running without it", exc_info=True)

    logger.info("failure-taxonomy service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    shutdown_observability(app)

    if worker_task is not None:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task

    await subscriber.stop()
    await event_publisher.close()

    if llm_client is not None:
        await llm_client.close()

    await db_engine.dispose()
    await cleanup()

    logger.info("failure-taxonomy service stopped")


def create_app(config: FailureTaxonomyConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = get_config()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="ARCHITECT Failure Taxonomy",
        description="Error classification, post-mortem analysis, and recovery strategies for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)
    init_observability(app, "failure-taxonomy")

    return app


def main() -> None:
    """CLI entry point: ``python -m failure_taxonomy.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "failure_taxonomy.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
