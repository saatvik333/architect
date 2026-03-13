"""Core evaluator that orchestrates multi-layer evaluation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.enums import EvalVerdict, EventType
from architect_common.logging import get_logger
from architect_common.types import TaskId, utcnow
from architect_events.schemas import EvalCompletedEvent, EventEnvelope
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.layers.compilation import CompilationLayer
from evaluation_engine.layers.unit_tests import UnitTestLayer
from evaluation_engine.models import EvaluationReport, LayerEvaluation

if TYPE_CHECKING:
    from architect_events.publisher import EventPublisher
    from architect_sandbox_client.client import SandboxClient

logger = get_logger(component="evaluation_engine.evaluator")


class Evaluator:
    """Orchestrates a multi-layer evaluation pipeline.

    Runs each configured layer in order, stops on FAIL_HARD (if ``fail_fast``
    is enabled), publishes events for each layer completion, and returns a
    full :class:`EvaluationReport`.
    """

    def __init__(
        self,
        sandbox_client: SandboxClient,
        event_publisher: EventPublisher,
        layers: list[EvalLayerBase] | None = None,
        *,
        fail_fast: bool = True,
    ) -> None:
        self._sandbox_client = sandbox_client
        self._event_publisher = event_publisher
        self._fail_fast = fail_fast

        # Default layer stack: compilation then unit tests
        if layers is not None:
            self._layers = layers
        else:
            self._layers = [
                CompilationLayer(sandbox_client),
                UnitTestLayer(sandbox_client),
            ]

    async def evaluate(
        self,
        task_id: TaskId,
        sandbox_session_id: str,
    ) -> EvaluationReport:
        """Run the full evaluation pipeline for a task.

        Args:
            task_id: The task being evaluated.
            sandbox_session_id: The sandbox session containing the code.

        Returns:
            An :class:`EvaluationReport` with all layer results and the
            computed overall verdict.
        """
        logger.info(
            "starting evaluation",
            task_id=str(task_id),
            sandbox_session_id=sandbox_session_id,
            layer_count=len(self._layers),
        )

        report = EvaluationReport(task_id=task_id, created_at=utcnow())
        layer_results = []

        for layer in self._layers:
            logger.info(
                "running layer",
                layer=layer.layer_name,
                task_id=str(task_id),
            )

            layer_eval = await layer.evaluate(sandbox_session_id)
            layer_results.append(layer_eval)

            # Publish a layer-completed event
            await self._publish_layer_event(task_id, layer_eval)

            logger.info(
                "layer complete",
                layer=layer.layer_name,
                verdict=layer_eval.verdict,
                task_id=str(task_id),
            )

            # Stop on FAIL_HARD if fail-fast is enabled
            if self._fail_fast and layer_eval.verdict == EvalVerdict.FAIL_HARD:
                logger.warning(
                    "fail-fast triggered",
                    layer=layer.layer_name,
                    task_id=str(task_id),
                )
                break

        # Reconstruct the report with all layer results (frozen model)
        report = EvaluationReport(
            task_id=task_id,
            layers=layer_results,
            overall_verdict=EvalVerdict.PASS,  # placeholder
            created_at=report.created_at,
        )
        overall = report.compute_overall_verdict()
        # Reconstruct with correct overall verdict
        report = EvaluationReport(
            task_id=task_id,
            layers=layer_results,
            overall_verdict=overall,
            created_at=report.created_at,
        )

        # Publish the final evaluation-completed event
        await self._publish_completed_event(report)

        logger.info(
            "evaluation complete",
            task_id=str(task_id),
            overall_verdict=overall,
            layers_run=len(layer_results),
        )

        return report

    async def _publish_layer_event(
        self,
        task_id: TaskId,
        layer_eval: LayerEvaluation,
    ) -> None:
        """Publish an eval.layer_completed event."""
        envelope = EventEnvelope(
            type=EventType.EVAL_LAYER_COMPLETED,
            payload={
                "task_id": str(task_id),
                "layer": layer_eval.layer,
                "verdict": layer_eval.verdict,
            },
        )
        await self._event_publisher.publish(envelope)

    async def _publish_completed_event(self, report: EvaluationReport) -> None:
        """Publish an eval.completed event with the full report summary."""
        layer_summaries = [
            {
                "layer": le.layer,
                "verdict": le.verdict,
            }
            for le in report.layers
        ]

        payload = EvalCompletedEvent(
            task_id=report.task_id,
            verdict=report.overall_verdict,
            layer_results=layer_summaries,
        )

        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload=payload.model_dump(),
        )
        await self._event_publisher.publish(envelope)
