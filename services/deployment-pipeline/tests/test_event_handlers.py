"""Tests for Deployment Pipeline event handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalVerdict, EventType
from architect_events.schemas import EventEnvelope
from deployment_pipeline.event_handlers import DeploymentEventHandler
from deployment_pipeline.pipeline_manager import PipelineManager


class TestDeploymentEventHandler:
    """Tests for the DeploymentEventHandler."""

    @pytest.fixture
    def mock_manager(self) -> AsyncMock:
        """Return a mock PipelineManager."""
        manager = AsyncMock(spec=PipelineManager)
        manager.start_deployment = AsyncMock()
        return manager

    @pytest.fixture
    def handler(self, mock_manager: AsyncMock) -> DeploymentEventHandler:
        """Return a handler with a mock manager."""
        return DeploymentEventHandler(mock_manager)

    async def test_eval_pass_triggers_deployment(
        self,
        handler: DeploymentEventHandler,
        mock_manager: AsyncMock,
    ) -> None:
        """EVAL_COMPLETED with PASS verdict should trigger deployment."""
        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "verdict": EvalVerdict.PASS,
                "task_id": "task-eval-1",
                "artifact_ref": "registry/app:v1.0.0",
                "summary": "All 7 layers passed.",
                "confidence": 0.97,
            },
        )

        await handler.handle_eval_completed(envelope)

        mock_manager.start_deployment.assert_called_once()
        call_kwargs = mock_manager.start_deployment.call_args
        artifact = call_kwargs.kwargs.get("artifact") or call_kwargs[1].get("artifact")
        assert artifact.task_id == "task-eval-1"
        assert artifact.artifact_ref == "registry/app:v1.0.0"

    async def test_eval_fail_does_not_trigger(
        self,
        handler: DeploymentEventHandler,
        mock_manager: AsyncMock,
    ) -> None:
        """EVAL_COMPLETED with FAIL verdict should not trigger deployment."""
        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "verdict": EvalVerdict.FAIL_SOFT,
                "task_id": "task-eval-2",
                "artifact_ref": "registry/app:v2.0.0",
                "confidence": 0.3,
            },
        )

        await handler.handle_eval_completed(envelope)

        mock_manager.start_deployment.assert_not_called()

    async def test_eval_pass_no_artifact_ref_skipped(
        self,
        handler: DeploymentEventHandler,
        mock_manager: AsyncMock,
    ) -> None:
        """EVAL_COMPLETED with PASS but no artifact_ref should be skipped."""
        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "verdict": EvalVerdict.PASS,
                "task_id": "task-eval-3",
                "artifact_ref": "",
                "confidence": 0.95,
            },
        )

        await handler.handle_eval_completed(envelope)

        mock_manager.start_deployment.assert_not_called()

    async def test_eval_hard_fail_does_not_trigger(
        self,
        handler: DeploymentEventHandler,
        mock_manager: AsyncMock,
    ) -> None:
        """EVAL_COMPLETED with FAIL_HARD verdict should not trigger deployment."""
        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "verdict": EvalVerdict.FAIL_HARD,
                "task_id": "task-eval-4",
                "artifact_ref": "registry/app:v4.0.0",
                "confidence": 0.0,
            },
        )

        await handler.handle_eval_completed(envelope)

        mock_manager.start_deployment.assert_not_called()

    async def test_confidence_passed_to_deployment(
        self,
        handler: DeploymentEventHandler,
        mock_manager: AsyncMock,
    ) -> None:
        """Confidence score should be forwarded to start_deployment."""
        envelope = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "verdict": EvalVerdict.PASS,
                "task_id": "task-eval-5",
                "artifact_ref": "registry/app:v5.0.0",
                "summary": "Passed",
                "confidence": 0.88,
            },
        )

        await handler.handle_eval_completed(envelope)

        call_kwargs = mock_manager.start_deployment.call_args
        confidence = call_kwargs.kwargs.get("confidence") or call_kwargs[1].get("confidence")
        assert confidence == 0.88
