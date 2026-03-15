"""FastAPI application factory for the Evaluation Engine service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from architect_common.logging import setup_logging
from evaluation_engine.api.dependencies import cleanup, get_config
from evaluation_engine.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Evaluation Engine."""
    config = get_config()
    setup_logging(log_level=config.log_level)
    yield
    await cleanup()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Evaluation Engine",
        description="Multi-layer code evaluation service for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def main() -> None:
    """CLI entry point: ``python -m evaluation_engine.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "evaluation_engine.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
