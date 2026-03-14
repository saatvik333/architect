"""Temporal activity definitions for the Spec Engine."""

from __future__ import annotations

from temporalio import activity

from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from spec_engine.config import SpecEngineConfig
from spec_engine.models import TaskSpec
from spec_engine.parser import SpecParser
from spec_engine.validator import SpecValidator

logger = get_logger(component="spec_engine.temporal.activities")


@activity.defn
async def parse_spec(
    raw_text: str,
    clarifications: dict[str, str] | None = None,
) -> dict:
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
async def validate_spec(spec_dict: dict) -> list[str]:
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
