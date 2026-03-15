"""Pydantic domain models for the Spec Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from architect_common.types import ArchitectBase, utcnow


class AcceptanceCriterion(ArchitectBase):
    """A single testable acceptance criterion extracted from natural language."""

    id: str = Field(default_factory=lambda: f"ac-{uuid.uuid4().hex[:8]}")
    description: str
    test_type: Literal["unit", "integration", "adversarial"] = "unit"
    automated: bool = True


class TaskSpec(ArchitectBase):
    """A formal specification derived from natural-language intent."""

    id: str = Field(default_factory=lambda: f"spec-{uuid.uuid4().hex[:12]}")
    intent: str
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    file_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ClarificationQuestion(ArchitectBase):
    """A question the engine needs answered before producing a complete spec."""

    question: str
    context: str = ""
    priority: Literal["high", "medium", "low"] = "medium"


class StakeholderConcern(ArchitectBase):
    """A concern raised by a simulated stakeholder persona."""

    role: str
    concern: str
    severity: Literal["low", "medium", "high"]
    suggestion: str


class StakeholderReview(ArchitectBase):
    """Aggregated review from multiple simulated stakeholder personas."""

    concerns: list[StakeholderConcern] = Field(default_factory=list)
    overall_risk: Literal["low", "medium", "high"] = "low"
    summary: str = ""


class ScopeConstraints(ArchitectBase):
    """Constraints that govern acceptable scope for a specification."""

    max_effort_hours: float = 40.0
    max_criteria: int = 20
    enforce_mvp: bool = True


class ScopeReport(ArchitectBase):
    """Report produced by the Scope Governor evaluating a spec's scope."""

    is_mvp: bool = True
    deferred_features: list[str] = Field(default_factory=list)
    scope_creep_flags: list[str] = Field(default_factory=list)
    estimated_effort_hours: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SpecResult(ArchitectBase):
    """Result of a spec parsing attempt — either a spec or clarification questions."""

    spec: TaskSpec | None = None
    needs_clarification: bool = False
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    stakeholder_review: StakeholderReview | None = None
    scope_report: ScopeReport | None = None
