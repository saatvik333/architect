"""Pydantic domain models for the Failure Taxonomy Engine."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from architect_common.enums import FailureCode
from architect_common.types import ArchitectBase, PostMortemId

# ── Classification models ────────────────────────────────────────────


class FailureClassification(ArchitectBase):
    """Result of classifying a failure into the taxonomy."""

    failure_code: FailureCode
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    root_cause: str | None = None
    suggested_fix: str | None = None


class ClassificationRequest(ArchitectBase):
    """Input for classifying a failure."""

    task_id: str
    agent_id: str | None = None
    error_message: str = ""
    stack_trace: str | None = None
    eval_layer: str | None = None
    eval_report: dict[str, Any] | None = None
    code_context: str | None = None


# ── Post-mortem models ───────────────────────────────────────────────


class PromptImprovement(ArchitectBase):
    """A suggested improvement to an agent's prompt."""

    target_agent_type: str
    current_prompt_excerpt: str = ""
    suggested_change: str
    rationale: str


class AdversarialTest(ArchitectBase):
    """A proposed adversarial test derived from failure analysis."""

    test_name: str
    test_description: str
    attack_vector: str
    expected_behavior: str


class HeuristicUpdate(ArchitectBase):
    """A proposed heuristic rule update."""

    domain: str
    condition: str
    action: str
    source_failure_codes: list[FailureCode] = Field(default_factory=list)


class TopologyRecommendation(ArchitectBase):
    """A recommendation for agent topology changes."""

    recommendation: str
    rationale: str
    estimated_impact: str


class PostMortemAnalysis(ArchitectBase):
    """Full post-mortem analysis output."""

    post_mortem_id: PostMortemId
    project_id: str
    failure_summary: dict[str, int] = Field(default_factory=dict)
    root_causes: list[str] = Field(default_factory=list)
    prompt_improvements: list[PromptImprovement] = Field(default_factory=list)
    adversarial_tests: list[AdversarialTest] = Field(default_factory=list)
    heuristic_updates: list[HeuristicUpdate] = Field(default_factory=list)
    topology_recommendations: list[TopologyRecommendation] = Field(default_factory=list)


# ── Simulation models ────────────────────────────────────────────────


class SimulationConfig(ArchitectBase):
    """Configuration for a simulation training run."""

    source_type: str = "manual"
    source_ref: str = ""
    bug_injection_count: int = Field(default=5, ge=1)
    max_duration_seconds: int = Field(default=300, ge=1)


class SimulationResult(ArchitectBase):
    """Result of a simulation training run."""

    failures_injected: int = 0
    failures_detected: int = 0
    detection_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    missed_failures: list[str] = Field(default_factory=list)
    false_positives: list[str] = Field(default_factory=list)
