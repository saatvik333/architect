"""Vector store using PostgreSQL + pgvector for semantic code search."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from codebase_comprehension.models import CodeChunk, EmbeddingResult

logger = structlog.get_logger()

try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    Vector = None

metadata = MetaData()

# Define the table schema to match init.sql
code_embeddings = Table(
    "code_embeddings",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("root_path", String, nullable=False),
    Column("file_path", String, nullable=False),
    Column("symbol_name", String, nullable=False),
    Column("symbol_kind", String, nullable=False),
    Column("line_number", Integer, nullable=False),
    Column("embedding", Vector(384) if _HAS_PGVECTOR else String, nullable=False),
    Column("source_chunk", Text, nullable=False),
    Column("metadata", JSONB, default={}),
)


class VectorStore:
    """Async vector store backed by PostgreSQL + pgvector.

    Stores code chunk embeddings and supports cosine similarity search.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: AsyncEngine | None = None

    async def _get_engine(self) -> AsyncEngine:
        """Lazy-create the async engine."""
        if self._engine is None:
            self._engine = create_async_engine(self._database_url, echo=False)
        return self._engine

    async def store_embeddings(
        self,
        root_path: str,
        embeddings: list[tuple[CodeChunk, list[float]]],
    ) -> int:
        """Store chunk embeddings in the database.

        Returns the number of rows inserted.
        """
        if not embeddings:
            return 0

        engine = await self._get_engine()
        rows: list[dict[str, Any]] = []
        for chunk, vector in embeddings:
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "root_path": root_path,
                    "file_path": chunk.file_path,
                    "symbol_name": chunk.symbol_name,
                    "symbol_kind": chunk.symbol_kind,
                    "line_number": chunk.line_number,
                    "embedding": vector,
                    "source_chunk": chunk.source,
                    "metadata": {},
                }
            )

        async with AsyncSession(engine) as session:
            await session.execute(code_embeddings.insert(), rows)
            await session.commit()

        return len(rows)

    async def search(
        self,
        query_embedding: list[float],
        root_path: str | None = None,
        limit: int = 20,
    ) -> list[EmbeddingResult]:
        """Search for similar code chunks using cosine distance.

        Returns results ordered by similarity (highest first).
        """
        engine = await self._get_engine()

        # Build the query using pgvector's cosine distance operator
        where_clause = ""
        params: dict[str, Any] = {"embedding": str(query_embedding), "limit": limit}
        if root_path is not None:
            where_clause = "WHERE root_path = :root_path"
            params["root_path"] = root_path

        query = text(f"""
            SELECT
                symbol_name,
                symbol_kind,
                file_path,
                line_number,
                source_chunk,
                1 - (embedding <=> :embedding::vector) AS score,
                metadata
            FROM code_embeddings
            {where_clause}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        async with AsyncSession(engine) as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        results: list[EmbeddingResult] = []
        for row in rows:
            results.append(
                EmbeddingResult(
                    symbol_name=row[0],
                    symbol_kind=row[1],
                    file_path=row[2],
                    line_number=row[3],
                    source_chunk=row[4],
                    score=float(row[5]),
                    metadata=row[6] or {},
                )
            )
        return results

    async def delete_index(self, root_path: str) -> int:
        """Delete all embeddings for a given root path.

        Returns the number of rows deleted.
        """
        engine = await self._get_engine()
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("DELETE FROM code_embeddings WHERE root_path = :root_path"),
                {"root_path": root_path},
            )
            await session.commit()
            return result.rowcount  # type: ignore[attr-defined, no-any-return]

    async def has_embeddings(self, root_path: str) -> bool:
        """Check whether embeddings exist for a given root path."""
        engine = await self._get_engine()
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("SELECT EXISTS(SELECT 1 FROM code_embeddings WHERE root_path = :root_path)"),
                {"root_path": root_path},
            )
            row = result.fetchone()
            return bool(row and row[0])

    async def close(self) -> None:
        """Dispose of the engine connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
