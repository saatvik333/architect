"""Pydantic domain models for the Evaluation Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.types import ArchitectBase, TaskId, utcnow

# ── Layer-specific result models ──────────────────────────────────────


class CompilationResult(ArchitectBase):
    """Result of a compilation/syntax-check layer."""

    success: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)


class TestFailureDetail(ArchitectBase):
    """Details about a single test failure."""

    test_name: str
    file_path: str = ""
    line_number: int | None = None
    message: str = ""
    traceback: str = ""


class UnitTestResult(ArchitectBase):
    """Result of a unit test layer."""

    total: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    failure_details: list[TestFailureDetail] = Field(default_factory=list)


class IntegrationTestResult(ArchitectBase):
    """Result of an integration test layer."""

    total: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    failure_details: list[TestFailureDetail] = Field(default_factory=list)


class AdversarialResult(ArchitectBase):
    """Result of an adversarial testing layer."""

    attack_vectors_tested: int = Field(default=0, ge=0)
    vulnerabilities_found: int = Field(default=0, ge=0)
    findings: list[str] = Field(default_factory=list)
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    duration_seconds: float = Field(default=0.0, ge=0.0)


class SpecComplianceResult(ArchitectBase):
    """Result of a spec-compliance evaluation layer."""

    criteria_total: int = Field(default=0, ge=0)
    criteria_met: int = Field(default=0, ge=0)
    criteria_unmet: list[str] = Field(default_factory=list)
    compliance_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ArchitectureResult(ArchitectBase):
    """Result of an architecture compliance layer."""

    violations: list[str] = Field(default_factory=list)
    conventions_checked: int = Field(default=0, ge=0)
    conventions_violated: int = Field(default=0, ge=0)
    import_violations: list[str] = Field(default_factory=list)


class RegressionResult(ArchitectBase):
    """Result of a regression testing layer."""

    baseline_test_count: int = Field(default=0, ge=0)
    regressions_found: int = Field(default=0, ge=0)
    regression_details: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)


# ── Layer evaluation envelope ─────────────────────────────────────────


class LayerEvaluation(ArchitectBase):
    """Result of running a single evaluation layer."""

    layer: EvalLayer
    verdict: EvalVerdict
    details: (
        CompilationResult
        | UnitTestResult
        | IntegrationTestResult
        | AdversarialResult
        | SpecComplianceResult
        | ArchitectureResult
        | RegressionResult
    )
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime = Field(default_factory=utcnow)


# ── Full evaluation report ────────────────────────────────────────────


class EvaluationReport(ArchitectBase):
    """Aggregate report for a full multi-layer evaluation run."""

    task_id: TaskId
    layers: list[LayerEvaluation] = Field(default_factory=list)
    overall_verdict: EvalVerdict = EvalVerdict.PASS
    created_at: datetime = Field(default_factory=utcnow)

    @staticmethod
    def compute_overall_verdict(layers: list[LayerEvaluation] | None = None) -> EvalVerdict:
        """Derive the overall verdict from individual layer verdicts.

        Args:
            layers: List of layer evaluations to compute verdict from.
                If ``None``, returns PASS (no layers means no failures).

        Returns:
            FAIL_HARD if any layer returned FAIL_HARD, FAIL_SOFT if any
            layer returned FAIL_SOFT, otherwise PASS.
        """
        if not layers:
            return EvalVerdict.PASS
        for layer_eval in layers:
            if layer_eval.verdict == EvalVerdict.FAIL_HARD:
                return EvalVerdict.FAIL_HARD
        for layer_eval in layers:
            if layer_eval.verdict == EvalVerdict.FAIL_SOFT:
                return EvalVerdict.FAIL_SOFT
        return EvalVerdict.PASS
