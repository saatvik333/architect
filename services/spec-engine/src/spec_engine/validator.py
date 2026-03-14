"""Spec validator — validates a TaskSpec for completeness and consistency."""

from __future__ import annotations

from spec_engine.models import TaskSpec


class SpecValidator:
    """Validates a :class:`TaskSpec` for structural correctness.

    The validator checks for common issues such as empty intent,
    missing success criteria, and duplicate criterion IDs.
    """

    def validate(self, spec: TaskSpec) -> list[str]:
        """Validate a spec and return a list of issues (empty means valid).

        Args:
            spec: The task specification to validate.

        Returns:
            A list of issue descriptions. An empty list means the spec is valid.
        """
        issues: list[str] = []

        # Intent must not be empty
        if not spec.intent.strip():
            issues.append("Intent must not be empty.")

        # Must have at least one success criterion if there are no open questions
        if not spec.success_criteria and not spec.open_questions:
            issues.append(
                "Spec must have at least one success criterion when there are no open questions."
            )

        # Check for duplicate criterion IDs
        criterion_ids = [c.id for c in spec.success_criteria]
        seen: set[str] = set()
        for cid in criterion_ids:
            if cid in seen:
                issues.append(f"Duplicate acceptance criterion ID: {cid}")
            seen.add(cid)

        # Criterion descriptions must not be empty
        for criterion in spec.success_criteria:
            if not criterion.description.strip():
                issues.append(f"Acceptance criterion {criterion.id} has an empty description.")

        return issues
