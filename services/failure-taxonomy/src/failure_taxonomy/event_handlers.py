"""Event handlers for the Failure Taxonomy service.

Subscribes to evaluation and task lifecycle events to automatically
classify failures and trigger post-mortem analysis.
"""

from __future__ import annotations

from typing import Any

from architect_common.enums import EvalVerdict, EventType, FailureCode
from architect_common.logging import get_logger
from architect_common.types import new_failure_record_id
from architect_db.models.failure import FailureRecord
from architect_db.repositories.failure_repo import (
    FailureRecordRepository,
)
from architect_events.publisher import EventPublisher
from architect_events.schemas import EventEnvelope, FailureClassifiedEvent

from .classifier import FailureClassifier
from .config import FailureTaxonomyConfig
from .models import ClassificationRequest

logger = get_logger(component="failure_taxonomy.event_handlers")


class FailureTaxonomyEventHandlers:
    """Handles incoming events from the event bus.

    Processes EVAL_COMPLETED (FAIL_HARD/FAIL_SOFT), TASK_FAILED, and
    DEPLOYMENT_ROLLED_BACK events by classifying failures and persisting them.
    """

    def __init__(
        self,
        config: FailureTaxonomyConfig,
        classifier: FailureClassifier,
        event_publisher: EventPublisher,
        session_factory: Any,
    ) -> None:
        self._config = config
        self._classifier = classifier
        self._publisher = event_publisher
        self._session_factory = session_factory

    async def handle_eval_completed(self, event: EventEnvelope) -> None:
        """Handle EVAL_COMPLETED events with FAIL_HARD or FAIL_SOFT verdict."""
        payload = event.payload
        verdict = payload.get("verdict", "")

        if verdict not in (EvalVerdict.FAIL_HARD, EvalVerdict.FAIL_SOFT):
            return

        task_id = str(payload.get("task_id", ""))
        raw_layers = payload.get("layer_results", [])
        layer_results: list[object] = list(raw_layers) if isinstance(raw_layers, list) else []

        # Build classification request from the failing layers
        error_messages: list[str] = []
        eval_layer: str | None = None
        for layer in layer_results:
            if isinstance(layer, dict) and layer.get("verdict") in ("fail_hard", "fail_soft"):
                eval_layer = layer.get("layer")
                msg = layer.get("message", "")
                if msg:
                    error_messages.append(str(msg))

        request = ClassificationRequest(
            task_id=task_id,
            error_message="\n".join(error_messages)
            if error_messages
            else f"Evaluation failed: {verdict}",
            eval_layer=eval_layer,
            eval_report={"layer_results": layer_results},
        )

        await self._classify_and_persist(request)

    async def handle_task_failed(self, event: EventEnvelope) -> None:
        """Handle TASK_FAILED events."""
        payload = event.payload
        task_id = str(payload.get("task_id", ""))
        agent_id = str(payload.get("agent_id", "")) or None
        error_message = str(payload.get("error_message", "Task failed"))

        request = ClassificationRequest(
            task_id=task_id,
            agent_id=agent_id,
            error_message=error_message,
        )

        await self._classify_and_persist(request)

    async def handle_deployment_rolled_back(self, event: EventEnvelope) -> None:
        """Handle DEPLOYMENT_ROLLED_BACK events."""
        payload = event.payload
        deployment_id = str(payload.get("deployment_id", ""))
        reason = str(payload.get("reason", "deployment_rolled_back"))

        request = ClassificationRequest(
            task_id=deployment_id,
            error_message=f"Deployment rolled back: {reason}",
        )

        await self._classify_and_persist(request)

    async def _classify_and_persist(self, request: ClassificationRequest) -> None:
        """Classify a failure and persist the record."""
        try:
            classification = await self._classifier.classify(request)

            async with self._session_factory() as session:
                repo = FailureRecordRepository(session)
                record = FailureRecord(
                    id=new_failure_record_id(),
                    task_id=request.task_id,
                    agent_id=request.agent_id,
                    failure_code=classification.failure_code.value,
                    severity=self._severity_for_code(classification.failure_code),
                    summary=classification.summary,
                    root_cause=classification.root_cause,
                    eval_layer=request.eval_layer,
                    error_message=request.error_message[:2000] if request.error_message else None,
                    stack_trace=request.stack_trace[:5000] if request.stack_trace else None,
                    classified_by="auto",
                    confidence=classification.confidence,
                )
                await repo.create(record)
                await session.commit()

            # Publish classification event
            await self._publisher.publish(
                EventEnvelope(
                    type=EventType.FAILURE_CLASSIFIED,
                    payload=FailureClassifiedEvent(
                        failure_record_id=record.id,
                        task_id=request.task_id,
                        failure_code=classification.failure_code,
                        confidence=classification.confidence,
                    ).model_dump(mode="json"),
                )
            )

            logger.info(
                "failure classified and persisted",
                task_id=request.task_id,
                failure_code=classification.failure_code,
                confidence=classification.confidence,
            )

        except Exception:
            logger.error(
                "failed to classify and persist failure",
                task_id=request.task_id,
                exc_info=True,
            )

    @staticmethod
    def _severity_for_code(code: FailureCode) -> str:
        """Map failure codes to severity levels."""
        critical = {FailureCode.F9_SECURITY_VULN}
        high = {FailureCode.F2_ARCHITECTURE_ERROR, FailureCode.F3_HALLUCINATION}
        low = {FailureCode.F7_UX_REJECTION}

        if code in critical:
            return "critical"
        if code in high:
            return "high"
        if code in low:
            return "low"
        return "medium"
