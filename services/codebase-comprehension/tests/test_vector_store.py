"""Tests for the VectorStore (mocked async database sessions)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebase_comprehension.models import CodeChunk
from codebase_comprehension.vector_store import VectorStore


@pytest.fixture
def sample_embeddings() -> list[tuple[CodeChunk, list[float]]]:
    """Return sample chunk-embedding pairs."""
    chunk1 = CodeChunk(
        file_path="helpers.py",
        symbol_name="greet",
        symbol_kind="function",
        line_number=1,
        end_line=3,
        source='def greet(name): return f"Hello, {name}!"',
    )
    chunk2 = CodeChunk(
        file_path="helpers.py",
        symbol_name="farewell",
        symbol_kind="function",
        line_number=5,
        end_line=7,
        source='def farewell(name): return f"Goodbye, {name}!"',
    )
    vec1 = [0.1] * 384
    vec2 = [0.2] * 384
    return [(chunk1, vec1), (chunk2, vec2)]


class TestStoreEmbeddings:
    """Test storing embeddings in the vector store."""

    @pytest.mark.asyncio
    async def test_store_returns_count(
        self, sample_embeddings: list[tuple[CodeChunk, list[float]]]
    ) -> None:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        vs._engine = mock_engine

        with patch(
            "codebase_comprehension.vector_store.AsyncSession",
            return_value=mock_session,
        ):
            count = await vs.store_embeddings("/project", sample_embeddings)

        assert count == 2
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_empty_returns_zero(self) -> None:
        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        count = await vs.store_embeddings("/project", [])
        assert count == 0


class TestSearch:
    """Test searching for similar embeddings."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        mock_row = (
            "greet",  # symbol_name
            "function",  # symbol_kind
            "helpers.py",  # file_path
            1,  # line_number
            "def greet(name): pass",  # source_chunk
            0.95,  # score
            {},  # metadata
        )

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()

        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        vs._engine = mock_engine

        with patch(
            "codebase_comprehension.vector_store.AsyncSession",
            return_value=mock_session,
        ):
            results = await vs.search([0.1] * 384, root_path="/project", limit=10)

        assert len(results) == 1
        assert results[0].symbol_name == "greet"
        assert results[0].score == 0.95


class TestDeleteIndex:
    """Test deleting embeddings for a root path."""

    @pytest.mark.asyncio
    async def test_delete_returns_rowcount(self) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()

        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        vs._engine = mock_engine

        with patch(
            "codebase_comprehension.vector_store.AsyncSession",
            return_value=mock_session,
        ):
            count = await vs.delete_index("/project")

        assert count == 5


class TestHasEmbeddings:
    """Test checking for existing embeddings."""

    @pytest.mark.asyncio
    async def test_has_embeddings_true(self) -> None:
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=True)

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()

        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        vs._engine = mock_engine

        with patch(
            "codebase_comprehension.vector_store.AsyncSession",
            return_value=mock_session,
        ):
            result = await vs.has_embeddings("/project")

        assert result is True

    @pytest.mark.asyncio
    async def test_has_embeddings_false(self) -> None:
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=False)

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_engine = AsyncMock()

        vs = VectorStore("postgresql+asyncpg://test:test@localhost/test")
        vs._engine = mock_engine

        with patch(
            "codebase_comprehension.vector_store.AsyncSession",
            return_value=mock_session,
        ):
            result = await vs.has_embeddings("/nonexistent")

        assert result is False
