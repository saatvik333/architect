"""FastAPI application factory for the Agent Communication Bus service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_comm_bus.api.dependencies import cleanup, get_config
from agent_comm_bus.api.routes import router
from architect_common.logging import setup_logging
from architect_observability import init_observability, shutdown_observability


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Agent Communication Bus."""
    config = get_config()
    setup_logging(log_level=config.log_level)
    yield
    shutdown_observability(app)
    await cleanup()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Agent Communication Bus",
        description="NATS JetStream typed inter-agent messaging for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    init_observability(app, "agent-comm-bus")
    return app


def main() -> None:
    """CLI entry point: ``python -m agent_comm_bus.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "agent_comm_bus.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
