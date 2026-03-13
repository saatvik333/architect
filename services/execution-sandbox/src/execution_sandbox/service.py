"""Main entry point for the Execution Sandbox service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from architect_common.logging import setup_logging
from execution_sandbox.api.dependencies import get_config
from execution_sandbox.api.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hook."""
    config = get_config()
    setup_logging(log_level=config.architect.log_level)
    yield


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Execution Sandbox",
        description="Isolated code execution service for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    """CLI entry point — run with ``python -m execution_sandbox.service``."""
    config = get_config()
    uvicorn.run(
        "execution_sandbox.service:app",
        host=config.host,
        port=config.port,
        log_level=config.architect.log_level.lower(),
    )


if __name__ == "__main__":
    main()
