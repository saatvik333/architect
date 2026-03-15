"""Tests for the core Evaluator orchestration logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict
from architect_common.types import TaskId, utcnow
from evaluation_engine.evaluator import Evaluator
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.models import (
    CompilationResult,
    EvaluationReport,
    LayerEvaluation,
    UnitTestResult,
)

# ── Stub layers for testing ──────────────────────────────────────────


class _StubLayer(EvalLayerBase):
    """A configurable stub layer for testing the evaluator."""

    def __init__(self, layer: EvalLayer, verdict: EvalVerdict) -> None:
        self._layer = layer
        self._verdict = verdict

    @property
    def layer_name(self) -> EvalLayer:
        return self._layer

    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        now = utcnow()
        if self._layer == EvalLayer.COMPILATION:
            details = CompilationResult(
                success=self._verdict == EvalVerdict.PASS,
                duration_seconds=0.1,
            )
        else:
            details = UnitTestResult(
                total=5,
                passed=5 if self._verdict == EvalVerdict.PASS else 3,
                failed=0 if self._verdict == EvalVerdict.PASS else 2,
                duration_seconds=0.5,
            )
        return LayerEvaluation(
            layer=self._layer,
            verdict=self._verdict,
            details=details,
            started_at=now,
            completed_at=now,
        )


# ── Tests ─────────────────────────────────────────────────────────────


class TestEvaluator:
    """Tests for the :class:`Evaluator` orchestrator."""

    @pytest.fixture
    def task_id(self) -> TaskId:
        return TaskId("task-test000001")

    async def test_all_layers_pass(
        self,
        mock_event_publisher: AsyncMock,
        mock_sandbox_client: AsyncMock,
        task_id: TaskId,
    ) -> None:
        """When all layers pass, overall verdict is PASS."""
        layers = [
            _StubLayer(EvalLayer.COMPILATION, EvalVerdict.PASS),
            _StubLayer(EvalLayer.UNIT_TESTS, EvalVerdict.PASS),
        ]
        evaluator = Evaluator(
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            layers=layers,
        )

        report = await evaluator.evaluate(task_id, "sbx-test000001")

        assert report.overall_verdict == EvalVerdict.PASS
        assert len(report.layers) == 2
        assert report.task_id == task_id

    async def test_fail_hard_stops_evaluation(
        self,
        mock_event_publisher: AsyncMock,
        mock_sandbox_client: AsyncMock,
        task_id: TaskId,
    ) -> None:
        """When a layer returns FAIL_HARD, subsequent layers are skipped."""
        layers = [
            _StubLayer(EvalLayer.COMPILATION, EvalVerdict.FAIL_HARD),
            _StubLayer(EvalLayer.UNIT_TESTS, EvalVerdict.PASS),
        ]
        evaluator = Evaluator(
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            layers=layers,
            fail_fast=True,
        )

        report = await evaluator.evaluate(task_id, "sbx-test000001")

        assert report.overall_verdict == EvalVerdict.FAIL_HARD
        assert len(report.layers) == 1  # unit tests were skipped
        assert report.layers[0].layer == EvalLayer.COMPILATION

    async def test_fail_soft_continues(
        self,
        mock_event_publisher: AsyncMock,
        mock_sandbox_client: AsyncMock,
        task_id: TaskId,
    ) -> None:
        """When a layer returns FAIL_SOFT, subsequent layers still run."""
        layers = [
            _StubLayer(EvalLayer.COMPILATION, EvalVerdict.PASS),
            _StubLayer(EvalLayer.UNIT_TESTS, EvalVerdict.FAIL_SOFT),
        ]
        evaluator = Evaluator(
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            layers=layers,
        )

        report = await evaluator.evaluate(task_id, "sbx-test000001")

        assert report.overall_verdict == EvalVerdict.FAIL_SOFT
        assert len(report.layers) == 2

    async def test_events_published_for_each_layer(
        self,
        mock_event_publisher: AsyncMock,
        mock_sandbox_client: AsyncMock,
        task_id: TaskId,
    ) -> None:
        """An event is published for each layer plus a final completed event."""
        layers = [
            _StubLayer(EvalLayer.COMPILATION, EvalVerdict.PASS),
            _StubLayer(EvalLayer.UNIT_TESTS, EvalVerdict.PASS),
        ]
        evaluator = Evaluator(
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            layers=layers,
        )

        await evaluator.evaluate(task_id, "sbx-test000001")

        # 2 layer events + 1 completed event = 3 publishes
        assert mock_event_publisher.publish.call_count == 3

    async def test_no_fail_fast_runs_all_layers(
        self,
        mock_event_publisher: AsyncMock,
        mock_sandbox_client: AsyncMock,
        task_id: TaskId,
    ) -> None:
        """With fail_fast=False, all layers run even after FAIL_HARD."""
        layers = [
            _StubLayer(EvalLayer.COMPILATION, EvalVerdict.FAIL_HARD),
            _StubLayer(EvalLayer.UNIT_TESTS, EvalVerdict.PASS),
        ]
        evaluator = Evaluator(
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            layers=layers,
            fail_fast=False,
        )

        report = await evaluator.evaluate(task_id, "sbx-test000001")

        assert report.overall_verdict == EvalVerdict.FAIL_HARD
        assert len(report.layers) == 2


class TestEvaluationReport:
    """Tests for the :meth:`EvaluationReport.compute_overall_verdict` method."""

    def test_all_pass(self) -> None:
        now = utcnow()
        report = EvaluationReport(
            task_id=TaskId("task-test000001"),
            layers=[
                LayerEvaluation(
                    layer=EvalLayer.COMPILATION,
                    verdict=EvalVerdict.PASS,
                    details=CompilationResult(success=True),
                    started_at=now,
                    completed_at=now,
                ),
            ],
        )
        assert EvaluationReport.compute_overall_verdict(report.layers) == EvalVerdict.PASS

    def test_fail_hard_dominates(self) -> None:
        now = utcnow()
        report = EvaluationReport(
            task_id=TaskId("task-test000001"),
            layers=[
                LayerEvaluation(
                    layer=EvalLayer.COMPILATION,
                    verdict=EvalVerdict.FAIL_SOFT,
                    details=CompilationResult(success=False),
                    started_at=now,
                    completed_at=now,
                ),
                LayerEvaluation(
                    layer=EvalLayer.UNIT_TESTS,
                    verdict=EvalVerdict.FAIL_HARD,
                    details=UnitTestResult(errors=1),
                    started_at=now,
                    completed_at=now,
                ),
            ],
        )
        assert EvaluationReport.compute_overall_verdict(report.layers) == EvalVerdict.FAIL_HARD

    def test_fail_soft_when_no_hard(self) -> None:
        now = utcnow()
        report = EvaluationReport(
            task_id=TaskId("task-test000001"),
            layers=[
                LayerEvaluation(
                    layer=EvalLayer.COMPILATION,
                    verdict=EvalVerdict.PASS,
                    details=CompilationResult(success=True),
                    started_at=now,
                    completed_at=now,
                ),
                LayerEvaluation(
                    layer=EvalLayer.UNIT_TESTS,
                    verdict=EvalVerdict.FAIL_SOFT,
                    details=UnitTestResult(failed=2),
                    started_at=now,
                    completed_at=now,
                ),
            ],
        )
        assert EvaluationReport.compute_overall_verdict(report.layers) == EvalVerdict.FAIL_SOFT

    def test_empty_layers(self) -> None:
        report = EvaluationReport(
            task_id=TaskId("task-test000001"),
            layers=[],
        )
        assert EvaluationReport.compute_overall_verdict(report.layers) == EvalVerdict.PASS
