"""Tests for the SpecValidator."""

from __future__ import annotations

from spec_engine.models import AcceptanceCriterion, TaskSpec
from spec_engine.validator import SpecValidator


class TestSpecValidator:
    """Tests for :class:`SpecValidator`."""

    def test_valid_spec_passes(self, sample_spec: TaskSpec) -> None:
        """A well-formed spec produces no validation issues."""
        validator = SpecValidator()
        issues = validator.validate(sample_spec)
        assert issues == []

    def test_empty_intent(self) -> None:
        """Spec with empty intent is flagged."""
        spec = TaskSpec(
            intent="",
            success_criteria=[
                AcceptanceCriterion(description="Something works", test_type="unit"),
            ],
        )
        validator = SpecValidator()
        issues = validator.validate(spec)
        assert any("intent" in i.lower() for i in issues)

    def test_missing_criteria_without_open_questions(self) -> None:
        """Spec with no criteria and no open questions is flagged."""
        spec = TaskSpec(
            intent="Build a thing",
            success_criteria=[],
            open_questions=[],
        )
        validator = SpecValidator()
        issues = validator.validate(spec)
        assert any("success criterion" in i.lower() for i in issues)

    def test_missing_criteria_with_open_questions_passes(self) -> None:
        """Spec with no criteria but open questions is acceptable."""
        spec = TaskSpec(
            intent="Build a thing",
            success_criteria=[],
            open_questions=["What database should we use?"],
        )
        validator = SpecValidator()
        issues = validator.validate(spec)
        assert issues == []

    def test_duplicate_criterion_ids(self) -> None:
        """Spec with duplicate criterion IDs is flagged."""
        spec = TaskSpec(
            intent="Build a thing",
            success_criteria=[
                AcceptanceCriterion(
                    id="ac-dup00001",
                    description="First criterion",
                    test_type="unit",
                ),
                AcceptanceCriterion(
                    id="ac-dup00001",
                    description="Second criterion",
                    test_type="integration",
                ),
            ],
        )
        validator = SpecValidator()
        issues = validator.validate(spec)
        assert any("duplicate" in i.lower() for i in issues)
