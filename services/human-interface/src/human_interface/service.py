"""FastAPI application factory for the Human Interface service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import partial

import httpx
from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_db.engine import create_engine, create_session_factory
from architect_events.publisher import EventPublisher
from architect_events.subscriber import EventSubscriber
from architect_observability import init_observability, shutdown_observability
from human_interface.api.dependencies import (
    cleanup,
    get_config,
    set_db_engine,
    set_http_client,
    set_ws_manager,
)
from human_interface.api.routes import router
from human_interface.config import HumanInterfaceConfig
from human_interface.event_handlers import handle_escalation_message, handle_system_event
from human_interface.ws_manager import WebSocketManager

logger = get_logger(component="human_interface.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Human Interface."""
    import time

    app.state.started_at = time.monotonic()
    config: HumanInterfaceConfig = app.state.config

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()
    app.state.event_publisher = event_publisher

    # ── WebSocket manager ────────────────────────────────────────────
    ws_manager = WebSocketManager()
    set_ws_manager(ws_manager)

    # ── HTTP client for upstream service calls ───────────────────────
    http_client = httpx.AsyncClient(timeout=10.0)
    set_http_client(http_client)

    # ── Database engine (shared across all requests) ─────────────────
    db_engine = create_engine(config.architect.postgres.dsn)
    session_factory = create_session_factory(db_engine)
    set_db_engine(db_engine, session_factory)

    # ── Event subscriptions ──────────────────────────────────────────
    subscriber = EventSubscriber(
        redis_url=config.architect.redis.url,
        group="human-interface",
        consumer="hi-1",
    )

    # Wrap handlers to inject the ws_manager dependency.
    subscriber.on(
        EventType.TASK_COMPLETED,
        partial(handle_system_event, ws_manager=ws_manager),
    )
    subscriber.on(
        EventType.TASK_FAILED,
        partial(handle_system_event, ws_manager=ws_manager),
    )
    subscriber.on(
        EventType.ESCALATION_CREATED,
        partial(handle_escalation_message, ws_manager=ws_manager),
    )
    subscriber.on(
        EventType.ESCALATION_RESOLVED,
        partial(handle_escalation_message, ws_manager=ws_manager),
    )

    event_types = [
        EventType.TASK_COMPLETED,
        EventType.TASK_FAILED,
        EventType.ESCALATION_CREATED,
        EventType.ESCALATION_RESOLVED,
    ]

    try:
        await subscriber.start(event_types)
        logger.info("event subscriber started")
    except Exception:
        logger.warning("event subscriber failed to start — running without it", exc_info=True)

    logger.info("human-interface service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    shutdown_observability(app)

    with suppress(asyncio.CancelledError):
        await subscriber.stop()
    await event_publisher.close()
    await cleanup()

    logger.info("human-interface service stopped")


def create_app(config: HumanInterfaceConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = get_config()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="ARCHITECT Human Interface",
        description="Human-in-the-loop approval workflows, escalation management, and real-time dashboard API.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)
    init_observability(app, "human-interface")

    return app


def main() -> None:
    """CLI entry point: ``python -m human_interface.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "human_interface.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
