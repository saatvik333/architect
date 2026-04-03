"""Tests for the cosine similarity utility."""

from __future__ import annotations

import pytest

from knowledge_memory.similarity import cosine_similarity


class TestCosineSimilarity:
    """Verify cosine_similarity edge cases and basic vector math."""

    def test_identical_vectors(self) -> None:
        """Identical vectors should yield similarity of 1.0."""
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors should yield similarity of 0.0."""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        """Opposite vectors should yield similarity of -1.0."""
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_empty_vectors(self) -> None:
        """Empty vectors should return 0.0."""
        assert cosine_similarity([], []) == 0.0

    def test_zero_magnitude_vector(self) -> None:
        """A zero-magnitude vector should return 0.0."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_both_zero_magnitude(self) -> None:
        """Two zero-magnitude vectors should return 0.0."""
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_different_lengths(self) -> None:
        """Vectors of different lengths should return 0.0."""
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_similar_vectors(self) -> None:
        """Similar but not identical vectors should yield a value close to 1.0."""
        a = [1.0, 2.0, 3.0]
        b = [1.1, 2.1, 3.1]
        result = cosine_similarity(a, b)
        assert 0.99 < result <= 1.0
