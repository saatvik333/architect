"""Event handlers for the Deployment Pipeline.

Subscribes to EVAL_COMPLETED events and triggers deployments when the
evaluation verdict is PASS.
"""

from __future__ import annotations

from typing import Any

from architect_common.enums import EvalVerdict
from architect_common.logging import get_logger
from architect_common.types import TaskId
from architect_events.schemas import EventEnvelope
from deployment_pipeline.models import DeploymentArtifact
from deployment_pipeline.pipeline_manager import PipelineManager

logger = get_logger(component="deployment_pipeline.event_handlers")


class DeploymentEventHandler:
    """Handles events that may trigger or affect deployments."""

    def __init__(self, pipeline_manager: PipelineManager) -> None:
        self._manager = pipeline_manager

    async def handle_eval_completed(self, envelope: EventEnvelope) -> None:
        """Handle EVAL_COMPLETED events.

        When an evaluation passes, extract the artifact reference and
        confidence score to start a deployment.
        """
        payload: dict[str, Any] = dict(envelope.payload)
        verdict = payload.get("verdict", "")
        task_id = payload.get("task_id", "")
        confidence = float(payload.get("confidence", 0.0))

        if verdict != EvalVerdict.PASS:
            logger.info(
                "eval verdict is not PASS — skipping deployment",
                task_id=task_id,
                verdict=verdict,
            )
            return

        artifact_ref = payload.get("artifact_ref", "")
        eval_summary = payload.get("summary", "")

        if not artifact_ref:
            logger.warning(
                "eval completed with PASS but no artifact_ref — skipping",
                task_id=task_id,
            )
            return

        artifact = DeploymentArtifact(
            task_id=TaskId(task_id),
            artifact_ref=artifact_ref,
            eval_report_summary=eval_summary,
        )

        logger.info(
            "eval passed — starting deployment",
            task_id=task_id,
            artifact_ref=artifact_ref,
            confidence=confidence,
        )

        await self._manager.start_deployment(
            artifact=artifact,
            eval_report=eval_summary,
            confidence=confidence,
        )
