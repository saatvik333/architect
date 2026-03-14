"""Tests for spec-engine domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spec_engine.models import AcceptanceCriterion, ClarificationQuestion, SpecResult, TaskSpec


class TestModels:
    """Tests for domain model behavior."""

    def test_frozen_behavior(self) -> None:
        """Models are immutable (frozen=True from ArchitectBase)."""
        spec = TaskSpec(intent="Do something")
        with pytest.raises(ValidationError):
            spec.intent = "Changed"  # type: ignore[misc]

    def test_default_factories(self) -> None:
        """Mutable defaults use independent factory instances."""
        spec_a = TaskSpec(intent="A")
        spec_b = TaskSpec(intent="B")
        # Ensure they have separate list instances
        assert spec_a.constraints is not spec_b.constraints
        assert spec_a.success_criteria is not spec_b.success_criteria
        assert spec_a.file_targets is not spec_b.file_targets

    def test_serialization_round_trip(self, sample_spec: TaskSpec) -> None:
        """TaskSpec survives JSON serialization and deserialization."""
        data = sample_spec.model_dump(mode="json")
        restored = TaskSpec.model_validate(data)

        assert restored.intent == sample_spec.intent
        assert restored.constraints == sample_spec.constraints
        assert len(restored.success_criteria) == len(sample_spec.success_criteria)
        assert restored.id == sample_spec.id

    def test_acceptance_criterion_defaults(self) -> None:
        """AcceptanceCriterion auto-generates ID and defaults."""
        criterion = AcceptanceCriterion(description="Tests pass")
        assert criterion.id.startswith("ac-")
        assert criterion.test_type == "unit"
        assert criterion.automated is True

    def test_spec_result_with_spec(self, sample_spec: TaskSpec) -> None:
        """SpecResult with a spec has needs_clarification=False by default."""
        result = SpecResult(spec=sample_spec)
        assert result.needs_clarification is False
        assert result.questions == []

    def test_spec_result_with_questions(self) -> None:
        """SpecResult with questions indicates clarification needed."""
        result = SpecResult(
            needs_clarification=True,
            questions=[
                ClarificationQuestion(
                    question="What framework?",
                    priority="high",
                ),
            ],
        )
        assert result.spec is None
        assert len(result.questions) == 1
        assert result.questions[0].context == ""
