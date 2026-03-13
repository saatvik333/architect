"""Pydantic domain models for the Evaluation Engine."""

from __future__ import annotations

from datetime import datetime

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


# ── Layer evaluation envelope ─────────────────────────────────────────


class LayerEvaluation(ArchitectBase):
    """Result of running a single evaluation layer."""

    layer: EvalLayer
    verdict: EvalVerdict
    details: CompilationResult | UnitTestResult
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime = Field(default_factory=utcnow)


# ── Full evaluation report ────────────────────────────────────────────


class EvaluationReport(ArchitectBase):
    """Aggregate report for a full multi-layer evaluation run."""

    task_id: TaskId
    layers: list[LayerEvaluation] = Field(default_factory=list)
    overall_verdict: EvalVerdict = EvalVerdict.PASS
    created_at: datetime = Field(default_factory=utcnow)

    def compute_overall_verdict(self) -> EvalVerdict:
        """Derive the overall verdict from individual layer verdicts.

        Returns:
            FAIL_HARD if any layer returned FAIL_HARD, FAIL_SOFT if any
            layer returned FAIL_SOFT, otherwise PASS.
        """
        for layer_eval in self.layers:
            if layer_eval.verdict == EvalVerdict.FAIL_HARD:
                return EvalVerdict.FAIL_HARD
        for layer_eval in self.layers:
            if layer_eval.verdict == EvalVerdict.FAIL_SOFT:
                return EvalVerdict.FAIL_SOFT
        return EvalVerdict.PASS
