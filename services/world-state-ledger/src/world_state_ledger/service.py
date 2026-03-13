"""Main service entry point for the World State Ledger."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI

from architect_common.logging import get_logger, setup_logging
from architect_db.engine import create_engine, create_session_factory
from architect_events.publisher import EventPublisher
from world_state_ledger.api.routes import router
from world_state_ledger.cache import StateCache
from world_state_ledger.config import WorldStateLedgerConfig
from world_state_ledger.event_log import EventLog
from world_state_ledger.state_manager import StateManager
from world_state_ledger.temporal.worker import start_temporal_worker

logger = get_logger(component="world_state_ledger.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialise and tear down infrastructure."""
    config: WorldStateLedgerConfig = app.state.config

    # ── Database ─────────────────────────────────────────────────────
    pg = config.architect.postgres
    engine = create_engine(pg.dsn, pool_min=pg.pool_min, pool_max=pg.pool_max)
    session_factory = create_session_factory(engine)

    # ── Redis ────────────────────────────────────────────────────────
    redis_client = aioredis.from_url(
        config.architect.redis.url,
        decode_responses=False,
    )
    state_cache = StateCache(redis_client)

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()

    # ── Service-layer objects ────────────────────────────────────────
    state_manager = StateManager(session_factory, state_cache, event_publisher)
    event_log = EventLog(session_factory)

    # Attach to app.state for dependency injection.
    app.state.state_manager = state_manager
    app.state.event_log = event_log
    app.state.state_cache = state_cache

    # ── Temporal worker (background task) ────────────────────────────
    temporal_worker = None
    temporal_task = None
    try:
        temporal_worker = await start_temporal_worker(config, state_manager, event_log)
        temporal_task = asyncio.create_task(temporal_worker.run())
        logger.info("temporal worker started in background")
    except Exception:
        logger.warning("temporal worker failed to start — running without it", exc_info=True)

    logger.info("world-state-ledger service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    if temporal_task is not None:
        temporal_task.cancel()
        with suppress(asyncio.CancelledError):
            await temporal_task

    await event_publisher.close()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("world-state-ledger service stopped")


def create_app(config: WorldStateLedgerConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = WorldStateLedgerConfig()

    setup_logging(log_level=config.architect.log_level)

    app = FastAPI(
        title="World State Ledger",
        description="Single source of truth for the ARCHITECT system",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)

    return app


def main() -> None:
    """CLI entry point — create the app and run it with uvicorn."""
    config = WorldStateLedgerConfig()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
