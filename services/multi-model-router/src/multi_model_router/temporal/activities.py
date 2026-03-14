"""Temporal activity definitions for the Multi-Model Router."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import TaskType
from architect_common.logging import get_logger
from architect_common.types import TaskId
from multi_model_router.config import MultiModelRouterConfig
from multi_model_router.router import Router
from multi_model_router.scorer import ComplexityScorer

logger = get_logger(component="multi_model_router.temporal.activities")


@activity.defn
async def route_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """Score and route a task to the appropriate model tier.

    Args:
        task_data: Dict with keys ``task_id``, ``task_type``, ``description``,
                   ``token_estimate``, and ``keywords``.

    Returns:
        A serialised :class:`RoutingDecision` dict.
    """
    activity.logger.info("route_task activity started")

    config = MultiModelRouterConfig()
    scorer = ComplexityScorer()
    router = Router(config=config)

    task_id = TaskId(task_data["task_id"])
    task_type = TaskType(task_data["task_type"])
    description = task_data.get("description", "")
    token_estimate = task_data.get("token_estimate", 0)
    keywords = task_data.get("keywords", [])

    complexity = scorer.score(
        task_type=task_type,
        description=description,
        token_estimate=token_estimate,
        keywords=keywords,
    )

    decision = router.route(
        task_id=task_id,
        task_type=task_type,
        complexity=complexity,
    )

    return decision.model_dump(mode="json")
