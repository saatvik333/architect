"""Tests for the EmbeddingGenerator (mocked sentence-transformers)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from codebase_comprehension.embeddings import EmbeddingGenerator
from codebase_comprehension.models import CodeChunk


@pytest.fixture
def sample_chunks() -> list[CodeChunk]:
    """Return a small list of code chunks for testing."""
    return [
        CodeChunk(
            file_path="helpers.py",
            symbol_name="greet",
            symbol_kind="function",
            line_number=1,
            end_line=3,
            source='def greet(name):\n    return f"Hello, {name}!"',
        ),
        CodeChunk(
            file_path="helpers.py",
            symbol_name="farewell",
            symbol_kind="function",
            line_number=5,
            end_line=7,
            source='def farewell(name):\n    return f"Goodbye, {name}!"',
        ),
    ]


@pytest.fixture
def mock_model() -> MagicMock:
    """Return a mock SentenceTransformer model."""
    model = MagicMock()
    # encode returns numpy arrays with shape (n, 384)
    model.encode.side_effect = lambda texts, **kwargs: np.random.rand(len(texts), 384).astype(
        np.float32
    )
    return model


class TestBatchEmbedding:
    """Test batch embedding of code chunks."""

    def test_embed_chunks(self, sample_chunks: list[CodeChunk], mock_model: MagicMock) -> None:
        generator = EmbeddingGenerator()
        generator._model = mock_model

        results = generator.embed_chunks(sample_chunks)

        assert len(results) == 2
        for _chunk, embedding in results:
            assert isinstance(embedding, list)
            assert len(embedding) == 384
            assert isinstance(embedding[0], float)

        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert len(call_args[0][0]) == 2  # Two text inputs

    def test_embed_empty_chunks(self, mock_model: MagicMock) -> None:
        generator = EmbeddingGenerator()
        generator._model = mock_model

        results = generator.embed_chunks([])

        assert results == []
        mock_model.encode.assert_not_called()


class TestQueryEmbedding:
    """Test single query embedding."""

    def test_embed_query(self, mock_model: MagicMock) -> None:
        generator = EmbeddingGenerator()
        generator._model = mock_model

        result = generator.embed_query("find the greet function")

        assert isinstance(result, list)
        assert len(result) == 384
        mock_model.encode.assert_called_once()


class TestModelLoading:
    """Test model lazy loading and error handling."""

    def test_import_error_raised_when_no_sentence_transformers(self) -> None:
        generator = EmbeddingGenerator()
        generator._model = None

        with (
            patch.dict("sys.modules", {"sentence_transformers": None}),
            pytest.raises(ImportError, match="sentence-transformers"),
        ):
            generator._get_model()

    def test_chunk_to_text_includes_context(self) -> None:
        chunk = CodeChunk(
            file_path="test.py",
            symbol_name="my_func",
            symbol_kind="function",
            line_number=1,
            end_line=3,
            source="def my_func(): pass",
            context="# This is a helper",
        )
        text = EmbeddingGenerator._chunk_to_text(chunk)
        assert "# This is a helper" in text
        assert "function my_func" in text
        assert "def my_func(): pass" in text
