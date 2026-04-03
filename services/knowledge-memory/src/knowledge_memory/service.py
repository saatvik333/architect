"""FastAPI application factory for the Knowledge & Memory service."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_events.subscriber import EventSubscriber
from architect_observability import init_observability, shutdown_observability
from knowledge_memory.api.dependencies import (
    cleanup,
    get_config,
    set_heuristic_engine,
    set_knowledge_store,
    set_working_memory,
)
from knowledge_memory.api.routes import router
from knowledge_memory.event_handler import KnowledgeEventHandler
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.working_memory import WorkingMemoryStore

logger = get_logger(component="knowledge_memory.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Knowledge & Memory service."""
    import time

    app.state.started_at = time.monotonic()
    config = get_config()
    setup_logging(log_level=config.log_level)

    # Initialize working memory store
    wm_store = WorkingMemoryStore(
        ttl_seconds=config.working_memory_ttl_seconds,
        max_entries=config.max_working_memory_entries,
    )
    set_working_memory(wm_store)

    # Initialize knowledge store (requires DB connection)
    # In production, this creates a real DB engine + session factory.
    # For initial startup without DB, we create a placeholder.
    store = None
    try:
        from architect_db.engine import create_engine, create_session_factory

        engine = create_engine(
            config.architect.postgres.dsn,
            pool_size=config.architect.postgres.pool_size,
            max_overflow=config.architect.postgres.max_overflow,
            pool_recycle=config.architect.postgres.pool_recycle,
            pool_timeout=config.architect.postgres.pool_timeout,
        )
        session_factory = create_session_factory(engine)
        store = KnowledgeStore(session_factory)
        set_knowledge_store(store)
        logger.info("knowledge store initialized with database connection")
    except Exception:
        logger.warning(
            "failed to initialize database connection, "
            "knowledge store will not be available until DB is configured"
        )

    # Initialize heuristic engine
    try:
        if store is not None:
            he = HeuristicEngine(
                knowledge_store=store,
            )
            set_heuristic_engine(he)
    except Exception:
        logger.warning("heuristic engine not initialized (no knowledge store)")

    # ── Event subscriptions ──────────────────────────────────────────
    subscriber: EventSubscriber | None = None
    if store is not None:
        try:
            event_handler = KnowledgeEventHandler(store)
            subscriber = EventSubscriber(
                redis_url=config.architect.redis.url,
                group="knowledge-memory",
                consumer="km-1",
            )
            subscriber.on(EventType.TASK_COMPLETED, event_handler.handle_task_completed)
            subscriber.on(EventType.TASK_FAILED, event_handler.handle_task_failed)

            await subscriber.start([EventType.TASK_COMPLETED, EventType.TASK_FAILED])
            logger.info("event subscriber started")
        except Exception:
            logger.warning(
                "event subscriber failed to start — running without it",
                exc_info=True,
            )
            subscriber = None

    # Start background task for working memory eviction
    eviction_task = asyncio.create_task(_eviction_loop(wm_store))

    logger.info("knowledge-memory service started", port=config.port)

    yield

    # Shutdown
    eviction_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await eviction_task

    if subscriber is not None:
        await subscriber.stop()

    shutdown_observability(app)
    await cleanup()
    logger.info("knowledge-memory service stopped")


async def _eviction_loop(wm_store: WorkingMemoryStore) -> None:
    """Periodically evict expired working memory entries."""
    while True:
        try:
            await asyncio.sleep(60)  # Run every 60 seconds
            evicted = await wm_store.evict_expired()
            if evicted > 0:
                logger.info("evicted expired working memory", count=evicted)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("error in working memory eviction loop")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Knowledge & Memory",
        description="Persistent learning and retrieval for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    init_observability(app, "knowledge-memory")
    return app


def main() -> None:
    """CLI entry point: ``python -m knowledge_memory.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "knowledge_memory.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
