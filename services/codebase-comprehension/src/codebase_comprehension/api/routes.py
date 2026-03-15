"""FastAPI route definitions for Codebase Comprehension."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus
from codebase_comprehension.api.dependencies import (
    get_architecture_map_generator,
    get_ast_indexer,
    get_config,
    get_context_assembler,
    get_index_store,
)
from codebase_comprehension.architecture_map import ArchitectureMapGenerator
from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import (
    ArchitectureMap,
    CodeContext,
    EmbeddingResult,
    SymbolInfo,
)

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


class EmbedRequest(BaseModel):
    """Request body for POST /api/v1/index/embed."""

    directory: str = Field(description="Absolute path to the directory to embed.")
    database_url: str = Field(
        default="postgresql+asyncpg://architect:architect_dev@localhost:5432/architect",
        description="Async database URL for pgvector storage.",
    )


class EmbedResponse(BaseModel):
    """Response body for POST /api/v1/index/embed."""

    root_path: str
    total_chunks: int
    total_embeddings: int


class ContextRequest(BaseModel):
    """Query parameters for GET /api/v1/context."""

    task_description: str = Field(description="Task description for context assembly.")
    max_tokens: int = Field(default=50_000, ge=1)


class SemanticSearchResponse(BaseModel):
    """Response body for GET /api/v1/context/semantic."""

    results: list[EmbeddingResult]
    total: int


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


@router.post("/api/v1/index/embed", response_model=EmbedResponse)
async def embed_index(body: EmbedRequest) -> EmbedResponse:
    """Generate embeddings for an indexed codebase and store in pgvector."""
    import pathlib

    from codebase_comprehension.chunker import SemanticChunker
    from codebase_comprehension.embeddings import EmbeddingGenerator
    from codebase_comprehension.tree_sitter_indexer import TreeSitterIndexer
    from codebase_comprehension.vector_store import VectorStore

    root = pathlib.Path(body.directory)
    indexer = TreeSitterIndexer()
    chunker = SemanticChunker()

    all_chunks = []
    for py_file in sorted(root.rglob("*.py")):
        if not py_file.is_file():
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel_path = str(py_file.relative_to(root))
        file_index = indexer.index_file(source, rel_path, "python")
        chunks = chunker.chunk_file(source, file_index)
        all_chunks.extend(chunks)

    total_embeddings = 0
    if all_chunks:
        generator = EmbeddingGenerator()
        embedded = generator.embed_chunks(all_chunks)
        vs = VectorStore(body.database_url)
        total_embeddings = await vs.store_embeddings(body.directory, embedded)
        await vs.close()

    return EmbedResponse(
        root_path=body.directory,
        total_chunks=len(all_chunks),
        total_embeddings=total_embeddings,
    )


@router.get("/api/v1/context", response_model=CodeContext)
async def get_context(
    task_description: str,
    max_tokens: int = 50_000,
    assembler: ContextAssembler = Depends(get_context_assembler),
) -> CodeContext:
    """Assemble code context for a task description."""
    return assembler.assemble(task_description, max_tokens=max_tokens)


@router.get("/api/v1/context/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    query: str,
    root_path: str | None = None,
    limit: int = 20,
    database_url: str = "postgresql+asyncpg://architect:architect_dev@localhost:5432/architect",
) -> SemanticSearchResponse:
    """Search for code using semantic similarity via pgvector."""
    from codebase_comprehension.embeddings import EmbeddingGenerator
    from codebase_comprehension.vector_store import VectorStore

    generator = EmbeddingGenerator()
    query_vec = generator.embed_query(query)

    vs = VectorStore(database_url)
    results = await vs.search(query_vec, root_path=root_path, limit=limit)
    await vs.close()

    return SemanticSearchResponse(results=results, total=len(results))


@router.get("/api/v1/architecture", response_model=ArchitectureMap)
async def get_architecture(
    root_path: str,
    store: IndexStore = Depends(get_index_store),
    generator: ArchitectureMapGenerator = Depends(get_architecture_map_generator),
) -> ArchitectureMap:
    """Generate an architecture map for an indexed codebase."""
    index = store.get(root_path)
    if index is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"No index found for {root_path}")
    return generator.generate(index)


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
