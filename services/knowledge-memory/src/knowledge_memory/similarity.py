"""Cosine similarity utility for embedding vectors.

Shared by :mod:`knowledge_store` and :mod:`pattern_extractor` to avoid
duplicating the vector math.
"""

from __future__ import annotations

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors.

    Returns 0.0 when either vector is empty, the vectors differ in length,
    or either has zero magnitude.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        A float in [-1, 1] representing the cosine of the angle between
        the two vectors.
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
