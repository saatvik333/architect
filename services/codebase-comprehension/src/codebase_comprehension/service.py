"""FastAPI application factory for the Codebase Comprehension service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from architect_common.logging import setup_logging
from codebase_comprehension.api.dependencies import cleanup, get_config
from codebase_comprehension.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Codebase Comprehension service."""
    config = get_config()
    setup_logging(log_level=config.log_level)

    # Optionally initialise vector store and embedding generator
    database_url = os.environ.get("CODEBASE_DATABASE_URL")
    if database_url:
        try:
            from codebase_comprehension.embeddings import EmbeddingGenerator
            from codebase_comprehension.vector_store import VectorStore

            app.state.vector_store = VectorStore(database_url)
            app.state.embedding_generator = EmbeddingGenerator()
        except ImportError:
            pass

    yield
    await cleanup()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="ARCHITECT Codebase Comprehension",
        description=(
            "Multi-language tree-sitter code indexing, semantic search via pgvector, "
            "and context assembly for the ARCHITECT system."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def main() -> None:
    """CLI entry point: ``python -m codebase_comprehension.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "codebase_comprehension.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
