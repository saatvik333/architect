"""FastAPI application factory for the Multi-Model Router service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from architect_common.logging import setup_logging
from multi_model_router.api.dependencies import cleanup, get_config
from multi_model_router.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Multi-Model Router."""
    config = get_config()
    setup_logging(log_level=config.log_level)
    yield
    await cleanup()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Multi-Model Router",
        description="Intelligent LLM routing and load balancing for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def main() -> None:
    """CLI entry point: ``python -m multi_model_router.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "multi_model_router.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
