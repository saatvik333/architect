"""Embedding generator using sentence-transformers."""

from __future__ import annotations

from typing import Any

import structlog

from codebase_comprehension.models import CodeChunk

logger = structlog.get_logger()


class EmbeddingGenerator:
    """Generate vector embeddings for code chunks using sentence-transformers.

    Falls back gracefully if sentence-transformers is not installed.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model: Any = None

    def _get_model(self) -> Any:
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer

            if self._device:
                self._model = SentenceTransformer(self._model_name, device=self._device)
            else:
                self._model = SentenceTransformer(self._model_name)
            return self._model
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embedding generation. "
                "Install it with: pip install sentence-transformers"
            ) from None

    def embed_chunks(self, chunks: list[CodeChunk]) -> list[tuple[CodeChunk, list[float]]]:
        """Batch-embed a list of code chunks.

        Returns a list of (chunk, embedding_vector) tuples.
        """
        if not chunks:
            return []

        model = self._get_model()
        texts = [self._chunk_to_text(chunk) for chunk in chunks]
        embeddings = model.encode(texts, show_progress_bar=False)

        results: list[tuple[CodeChunk, list[float]]] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            results.append((chunk, embedding.tolist()))
        return results

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Returns the embedding as a list of floats.
        """
        model = self._get_model()
        embedding = model.encode([text], show_progress_bar=False)
        return embedding[0].tolist()  # type: ignore[no-any-return]

    @staticmethod
    def _chunk_to_text(chunk: CodeChunk) -> str:
        """Convert a code chunk to a text representation for embedding."""
        parts: list[str] = []
        if chunk.context:
            parts.append(chunk.context)
        parts.append(f"{chunk.symbol_kind} {chunk.symbol_name}")
        parts.append(chunk.source)
        return "\n".join(parts)
