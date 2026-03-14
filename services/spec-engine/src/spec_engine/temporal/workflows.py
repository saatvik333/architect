"""Temporal workflow definitions for the Spec Engine."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from spec_engine.temporal.activities import parse_spec, validate_spec


@workflow.defn
class SpecificationWorkflow:
    """Temporal workflow that orchestrates specification parsing and validation.

    Steps: parse raw text -> validate spec -> return result.
    """

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the specification pipeline.

        Args:
            input_data: Dict with ``raw_text`` (str) and optional
                ``clarifications`` (dict[str, str]).

        Returns:
            A dict with ``result`` (serialised SpecResult) and
            ``validation_issues`` (list of strings).
        """
        # Version gate: establishes baseline for future behavioral changes.
        workflow.patched("v1-spec-engine-baseline")

        raw_text = input_data.get("raw_text", "")
        clarifications = input_data.get("clarifications")

        # Step 1: Parse the raw text into a spec or clarification questions
        result_dict = await workflow.execute_activity(
            parse_spec,
            args=[raw_text, clarifications],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 2: Validate the spec if one was produced
        validation_issues: list[str] = []
        if result_dict.get("spec") is not None:
            validation_issues = await workflow.execute_activity(
                validate_spec,
                args=[result_dict["spec"]],
                start_to_close_timeout=timedelta(minutes=1),
            )

        return {
            "result": result_dict,
            "validation_issues": validation_issues,
        }
