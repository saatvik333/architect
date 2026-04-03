"""Meta-strategy A/B testing and validation for the Knowledge & Memory system.

Provides deterministic assignment of strategies to tasks, outcome tracking,
and statistical evaluation to promote or reject strategies based on evidence.
"""

from __future__ import annotations

import hashlib
import math

from architect_common.logging import get_logger
from knowledge_memory.models import MetaStrategy

logger = get_logger(component="strategy_validator")


def assign_ab_group(task_id: str, ab_test_id: str) -> str:
    """Deterministically assign a task to 'control' or 'experiment'.

    Uses a hash of (task_id + ab_test_id) so the assignment is consistent
    for the same task/test combination but random-looking across tasks.
    """
    key = f"{task_id}:{ab_test_id}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    # Use last byte as a simple split
    last_byte = int(digest[-2:], 16)
    return "experiment" if last_byte < 128 else "control"


def record_outcome(strategy: MetaStrategy, success: bool) -> MetaStrategy:
    """Record a task outcome for a strategy.

    Returns a new MetaStrategy with updated counters (immutable model).
    """
    new_applied = strategy.tasks_applied + 1
    new_succeeded = strategy.tasks_succeeded + (1 if success else 0)
    new_failed = strategy.tasks_failed + (0 if success else 1)

    return strategy.model_copy(
        update={
            "tasks_applied": new_applied,
            "tasks_succeeded": new_succeeded,
            "tasks_failed": new_failed,
        }
    )


def evaluate_strategy(
    strategy: MetaStrategy,
    baseline_success_rate: float = 0.5,
    min_samples: int = 30,
    significance_threshold: float = 0.05,
) -> str:
    """Evaluate whether a strategy should be promoted or rejected.

    Uses a simple proportion test comparing the strategy's success rate
    against the baseline.

    Returns:
        - ``"insufficient_data"`` if not enough samples
        - ``"validated"`` if significantly better than baseline
        - ``"rejected"`` if significantly worse than baseline
        - ``"inconclusive"`` if no significant difference
    """
    n = strategy.tasks_applied
    if n < min_samples:
        return "insufficient_data"

    observed_rate = strategy.tasks_succeeded / n if n > 0 else 0.0

    # Standard error for a proportion test
    se = math.sqrt(baseline_success_rate * (1 - baseline_success_rate) / n)
    if se == 0:
        return "inconclusive"

    z_score = (observed_rate - baseline_success_rate) / se

    # Two-tailed test
    # z > 1.96 → significantly better (p < 0.05)
    # z < -1.96 → significantly worse (p < 0.05)
    if z_score > 1.96:
        return "validated"
    if z_score < -1.96:
        return "rejected"
    return "inconclusive"


def get_success_rate(strategy: MetaStrategy) -> float:
    """Calculate the success rate for a strategy."""
    if strategy.tasks_applied == 0:
        return 0.0
    return strategy.tasks_succeeded / strategy.tasks_applied


async def run_validation_cycle(
    strategies: list[MetaStrategy],
    baseline_success_rate: float = 0.5,
    min_samples: int = 30,
) -> dict[str, list[MetaStrategy]]:
    """Run validation on a batch of strategies.

    Returns a dict with keys 'validated', 'rejected', 'inconclusive',
    'insufficient_data', each containing the matching strategies.
    """
    results: dict[str, list[MetaStrategy]] = {
        "validated": [],
        "rejected": [],
        "inconclusive": [],
        "insufficient_data": [],
    }

    for strategy in strategies:
        if strategy.validation_status in ("validated", "rejected"):
            continue  # Already finalized

        verdict = evaluate_strategy(
            strategy,
            baseline_success_rate=baseline_success_rate,
            min_samples=min_samples,
        )
        results[verdict].append(strategy)

        if verdict in ("validated", "rejected"):
            logger.info(
                "strategy_evaluation_result",
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                verdict=verdict,
                success_rate=round(get_success_rate(strategy), 3),
                samples=strategy.tasks_applied,
            )

    logger.info(
        "validation_cycle_complete",
        total=len(strategies),
        validated=len(results["validated"]),
        rejected=len(results["rejected"]),
        inconclusive=len(results["inconclusive"]),
    )

    return results
