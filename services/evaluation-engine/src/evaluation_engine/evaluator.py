"""Core evaluator that orchestrates multi-layer evaluation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.enums import EvalVerdict, EventType
from architect_common.logging import get_logger
from architect_common.types import TaskId, utcnow
from architect_events.schemas import EvalCompletedEvent, EventEnvelope
from evaluation_engine.layers.adversarial import AdversarialLayer
from evaluation_engine.layers.architecture import ArchitectureComplianceLayer
from evaluation_engine.layers.base import EvalLayerBase
from evaluation_engine.layers.compilation import CompilationLayer
from evaluation_engine.layers.integration_tests import IntegrationTestLayer
from evaluation_engine.layers.regression import RegressionLayer
from evaluation_engine.layers.spec_compliance import SpecComplianceLayer
from evaluation_engine.layers.unit_tests import UnitTestLayer
from evaluation_engine.models import EvaluationReport, LayerEvaluation

if TYPE_CHECKING:
    from architect_events.publisher import EventPublisher
    from architect_llm.client import LLMClient
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
        llm_client: LLMClient | None = None,
        acceptance_criteria: list[str] | None = None,
        fail_fast: bool = True,
    ) -> None:
        self._sandbox_client = sandbox_client
        self._event_publisher = event_publisher
        self._fail_fast = fail_fast

        if layers is not None:
            self._layers = layers
        else:
            default_layers: list[EvalLayerBase] = [
                CompilationLayer(sandbox_client),
                UnitTestLayer(sandbox_client),
                IntegrationTestLayer(sandbox_client),
            ]
            if llm_client is not None:
                default_layers.append(AdversarialLayer(sandbox_client, llm_client))
            default_layers.append(SpecComplianceLayer(sandbox_client, acceptance_criteria))
            default_layers.append(ArchitectureComplianceLayer(sandbox_client))
            default_layers.append(RegressionLayer(sandbox_client))
            self._layers = default_layers

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

        # Compute overall verdict from layer results, then build the final report
        temp = EvaluationReport(
            task_id=task_id,
            layers=layer_results,
            overall_verdict=EvalVerdict.PASS,
            created_at=report.created_at,
        )
        report = EvaluationReport(
            task_id=task_id,
            layers=layer_results,
            overall_verdict=temp.compute_overall_verdict(),
            created_at=report.created_at,
        )

        # Publish the final evaluation-completed event
        await self._publish_completed_event(report)

        logger.info(
            "evaluation complete",
            task_id=str(task_id),
            overall_verdict=report.overall_verdict,
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
