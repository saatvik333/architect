"""Temporal activity definitions for the Multi-Model Router."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import TaskType
from architect_common.logging import get_logger
from architect_common.types import TaskId
from architect_llm.cost_tracker import _resolve_pricing
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
                   Optional: ``input_tokens``, ``output_tokens`` for cost tracking.

    Returns:
        A serialised :class:`RoutingDecision` dict, augmented with cost fields:
        ``cost_usd``, ``input_tokens``, ``output_tokens``.
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
    input_tokens = task_data.get("input_tokens", 0)
    output_tokens = task_data.get("output_tokens", 0)

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

    # Compute cost for the routed model
    input_price, output_price = _resolve_pricing(decision.model_id)
    cost_usd = (input_tokens * input_price) + (output_tokens * output_price)

    result = decision.model_dump(mode="json")
    result["cost_usd"] = round(cost_usd, 8)
    result["input_tokens"] = input_tokens
    result["output_tokens"] = output_tokens

    return result
