"""Failure analysis and heuristic feedback for the Knowledge & Memory system.

Classifies task failures and feeds outcomes back into the heuristic engine
to adjust confidence scores and deactivate ineffective heuristics.
"""

from __future__ import annotations

import re

from architect_common.logging import get_logger
from architect_common.types import HeuristicId
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.models import HeuristicRule

logger = get_logger(component="failure_analyzer")

# ── Failure category patterns ────────────────────────────────────────

_CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("compilation", re.compile(r"SyntaxError|IndentationError|NameError", re.IGNORECASE)),
    ("import_error", re.compile(r"ImportError|ModuleNotFoundError", re.IGNORECASE)),
    ("test_failure", re.compile(r"AssertionError|assert\s+.*failed", re.IGNORECASE)),
    ("timeout", re.compile(r"TimeoutError|timed?\s*out", re.IGNORECASE)),
    ("resource_exhaustion", re.compile(r"MemoryError|OOM|out\s+of\s+memory", re.IGNORECASE)),
    ("security_violation", re.compile(r"SecurityError|permission\s+denied", re.IGNORECASE)),
    (
        "dependency_error",
        re.compile(r"dependency|package\s+not\s+found|version\s+conflict", re.IGNORECASE),
    ),
    (
        "runtime_error",
        re.compile(r"RuntimeError|TypeError|ValueError|KeyError|AttributeError", re.IGNORECASE),
    ),
]


def classify_failure(error_message: str) -> str:
    """Classify an error message into a failure category.

    Returns a category string like ``"compilation"``, ``"import_error"``, etc.
    Falls back to ``"unknown"`` if no pattern matches.
    """
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(error_message):
            return category
    return "unknown"


async def record_heuristic_failure(
    heuristic_engine: HeuristicEngine,
    heuristic_ids: list[str],
) -> list[str]:
    """Downgrade confidence for heuristics implicated in a failure.

    Returns the list of heuristic IDs that were downgraded.
    """
    downgraded: list[str] = []
    for heuristic_id in heuristic_ids:
        await heuristic_engine.evolve_heuristic(HeuristicId(heuristic_id), success=False)
        downgraded.append(heuristic_id)
        logger.info(
            "heuristic_downgraded",
            heuristic_id=heuristic_id,
            reason="failure_recorded",
        )
    return downgraded


async def review_heuristic_effectiveness(
    heuristic_engine: HeuristicEngine,
    failure_threshold: float = 0.5,
    min_samples: int = 5,
) -> list[HeuristicRule]:
    """Find heuristics with high failure rates.

    Returns heuristics where ``failure_count / total > failure_threshold``
    and ``total >= min_samples``.
    """
    all_heuristics = await heuristic_engine.match_heuristics()
    ineffective: list[HeuristicRule] = []

    for h in all_heuristics:
        total = h.success_count + h.failure_count
        if total < min_samples:
            continue
        failure_rate = h.failure_count / total
        if failure_rate > failure_threshold:
            ineffective.append(h)
            logger.info(
                "ineffective_heuristic_found",
                heuristic_id=h.id,
                failure_rate=round(failure_rate, 3),
                total_samples=total,
            )

    return ineffective
