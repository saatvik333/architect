"""FastAPI application factory for the Coding Agent service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from architect_common.logging import setup_logging
from coding_agent.api.dependencies import cleanup, get_config
from coding_agent.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Coding Agent."""
    config = get_config()
    setup_logging(log_level=config.log_level)
    yield
    await cleanup()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Coding Agent",
        description="Core coding agent service for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    """CLI entry point: ``python -m coding_agent.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "coding_agent.service:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
