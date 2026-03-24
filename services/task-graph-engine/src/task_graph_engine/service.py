"""Main entry point for the Task Graph Engine service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from architect_common.logging import get_logger, setup_logging
from architect_observability import init_observability, shutdown_observability
from task_graph_engine.api.routes import router
from task_graph_engine.config import TaskGraphEngineConfig

logger = get_logger(component="task_graph_engine_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown lifecycle for the service."""
    logger.info("Task Graph Engine starting up")
    yield
    shutdown_observability(app)
    logger.info("Task Graph Engine shutting down")

    # Clean up the event publisher if it was created.
    from task_graph_engine.api.dependencies import _event_publisher

    if _event_publisher is not None:
        await _event_publisher.close()


def create_app(config: TaskGraphEngineConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Service configuration.  If ``None``, settings are loaded
                from environment variables.

    Returns:
        A fully configured :class:`FastAPI` application.
    """
    if config is None:
        config = TaskGraphEngineConfig()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="Task Graph Engine",
        description="DAG-based task decomposition and scheduling for ARCHITECT",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(router, tags=["tasks"])
    init_observability(app, "task-graph-engine")

    return app


def main() -> None:
    """Run the service with Uvicorn."""
    config = TaskGraphEngineConfig()
    setup_logging(log_level=config.log_level)

    logger.info(
        "Starting Task Graph Engine",
        host=config.host,
        port=config.port,
    )

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
