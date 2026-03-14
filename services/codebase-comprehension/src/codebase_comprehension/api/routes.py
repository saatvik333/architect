"""FastAPI route definitions for Codebase Comprehension."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus
from codebase_comprehension.api.dependencies import (
    get_ast_indexer,
    get_config,
    get_context_assembler,
    get_index_store,
)
from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import CodeContext, SymbolInfo

router = APIRouter()


# -- Request / Response schemas ---------------------------------------------


class IndexRequest(BaseModel):
    """Request body for POST /api/v1/index."""

    directory: str = Field(description="Absolute path to the directory to index.")
    glob_pattern: str = Field(
        default="**/*.py",
        description="Glob pattern for files to include.",
    )


class IndexResponse(BaseModel):
    """Response body for POST /api/v1/index."""

    root_path: str
    total_files: int
    total_symbols: int


class ContextRequest(BaseModel):
    """Query parameters for GET /api/v1/context."""

    task_description: str = Field(description="Task description for context assembly.")
    max_tokens: int = Field(default=50_000, ge=1)


class SymbolsResponse(BaseModel):
    """Response body for GET /api/v1/symbols."""

    symbols: list[SymbolInfo]
    total: int


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "codebase-comprehension"
    status: HealthStatus


# -- Endpoints ---------------------------------------------------------------


@router.post("/api/v1/index", response_model=IndexResponse)
async def index_directory(
    body: IndexRequest,
    indexer: ASTIndexer = Depends(get_ast_indexer),
    store: IndexStore = Depends(get_index_store),
) -> IndexResponse:
    """Index a directory and store the result."""
    config = get_config()
    index = indexer.index_directory(
        body.directory,
        body.glob_pattern,
        max_files=config.max_files_per_index,
    )
    store.store(index)
    return IndexResponse(
        root_path=index.root_path,
        total_files=index.total_files,
        total_symbols=index.total_symbols,
    )


@router.get("/api/v1/context", response_model=CodeContext)
async def get_context(
    task_description: str,
    max_tokens: int = 50_000,
    assembler: ContextAssembler = Depends(get_context_assembler),
) -> CodeContext:
    """Assemble code context for a task description."""
    return assembler.assemble(task_description, max_tokens=max_tokens)


@router.get("/api/v1/symbols", response_model=SymbolsResponse)
async def search_symbols(
    query: str,
    limit: int = 20,
    store: IndexStore = Depends(get_index_store),
) -> SymbolsResponse:
    """Search for symbols by name (case-insensitive substring match)."""
    symbols = store.search_symbols(query, limit=limit)
    return SymbolsResponse(symbols=symbols, total=len(symbols))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)
