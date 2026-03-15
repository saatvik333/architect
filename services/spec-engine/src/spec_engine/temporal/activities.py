"""Temporal activity definitions for the Spec Engine."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from spec_engine.config import SpecEngineConfig
from spec_engine.models import ScopeConstraints, TaskSpec
from spec_engine.parser import SpecParser
from spec_engine.scope_governor import ScopeGovernor
from spec_engine.stakeholder_simulator import StakeholderSimulator
from spec_engine.validator import SpecValidator

logger = get_logger(component="spec_engine.temporal.activities")


@activity.defn
async def parse_spec(
    raw_text: str,
    clarifications: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Parse raw text into a SpecResult.

    Args:
        raw_text: Natural-language requirement text.
        clarifications: Optional question→answer pairs from prior round.

    Returns:
        A serialised :class:`SpecResult` dict.
    """
    activity.logger.info("parse_spec activity started")

    config = SpecEngineConfig()
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.architect.claude.model_id,
    )

    try:
        parser = SpecParser(llm_client)
        result = await parser.parse(raw_text, clarifications=clarifications)
        return result.model_dump(mode="json")
    finally:
        await llm_client.close()


@activity.defn
async def validate_spec(spec_dict: dict[str, Any]) -> list[str]:
    """Validate a spec and return a list of issues.

    Args:
        spec_dict: A serialised :class:`TaskSpec` dict.

    Returns:
        A list of validation issue strings (empty = valid).
    """
    activity.logger.info("validate_spec activity started")

    spec = TaskSpec.model_validate(spec_dict)
    validator = SpecValidator()
    return validator.validate(spec)


@activity.defn
async def simulate_stakeholders(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Run stakeholder simulation on a spec.

    Args:
        spec_dict: A serialised :class:`TaskSpec` dict.

    Returns:
        A serialised :class:`StakeholderReview` dict.
    """
    activity.logger.info("simulate_stakeholders activity started")

    config = SpecEngineConfig()
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.architect.claude.model_id,
    )

    try:
        spec = TaskSpec.model_validate(spec_dict)
        simulator = StakeholderSimulator(llm_client)
        review = await simulator.simulate(spec)
        return review.model_dump(mode="json")
    finally:
        await llm_client.close()


@activity.defn
async def govern_scope(
    spec_dict: dict[str, Any],
    constraints_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a spec's scope against constraints.

    Args:
        spec_dict: A serialised :class:`TaskSpec` dict.
        constraints_dict: Optional serialised :class:`ScopeConstraints` dict.

    Returns:
        A serialised :class:`ScopeReport` dict.
    """
    activity.logger.info("govern_scope activity started")

    config = SpecEngineConfig()
    llm_client = LLMClient(
        api_key=config.architect.claude.api_key.get_secret_value(),
        default_model=config.architect.claude.model_id,
    )

    try:
        spec = TaskSpec.model_validate(spec_dict)
        constraints = (
            ScopeConstraints.model_validate(constraints_dict)
            if constraints_dict is not None
            else None
        )
        governor = ScopeGovernor(llm_client)
        report = await governor.evaluate(spec, constraints=constraints)
        return report.model_dump(mode="json")
    finally:
        await llm_client.close()
