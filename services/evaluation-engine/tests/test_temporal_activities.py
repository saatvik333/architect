"""Tests for Evaluation Engine Temporal activities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from architect_common.enums import EvalVerdict
from evaluation_engine.temporal.activities import run_evaluation

# ---------------------------------------------------------------------------
# run_evaluation
# ---------------------------------------------------------------------------


class TestRunEvaluation:
    """Tests for the run_evaluation activity."""

    @patch("evaluation_engine.temporal.activities.activity")
    @patch("evaluation_engine.temporal.activities.EventPublisher")
    @patch("evaluation_engine.temporal.activities.SandboxClient")
    @patch("evaluation_engine.temporal.activities.Evaluator")
    @patch("evaluation_engine.temporal.activities.EvaluationEngineConfig")
    async def test_returns_evaluation_report_dict(
        self,
        mock_config_cls: MagicMock,
        mock_evaluator_cls: MagicMock,
        mock_sandbox_cls: MagicMock,
        mock_publisher_cls: MagicMock,
        mock_activity: MagicMock,
    ) -> None:
        """run_evaluation should return a serialised EvaluationReport dict."""
        mock_activity.logger = MagicMock()

        # Set up config mock
        mock_config = MagicMock()
        mock_config.sandbox_base_url = "http://localhost:8002"
        mock_config.architect.redis.url = "redis://localhost:6379"
        mock_config.fail_fast = True
        mock_config_cls.return_value = mock_config

        # Set up sandbox client mock
        mock_sandbox = AsyncMock()
        mock_sandbox.close = AsyncMock()
        mock_sandbox_cls.return_value = mock_sandbox

        # Set up event publisher mock
        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        # Set up evaluator mock
        mock_evaluator_instance = AsyncMock()
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "task_id": "task-test000001",
            "layers": [],
            "overall_verdict": EvalVerdict.PASS.value,
        }
        mock_evaluator_instance.evaluate.return_value = mock_report
        mock_evaluator_cls.return_value = mock_evaluator_instance

        result = await run_evaluation("task-test000001", "sbx-session001")

        assert isinstance(result, dict)
        assert result["task_id"] == "task-test000001"
        assert result["overall_verdict"] == EvalVerdict.PASS.value

    @patch("evaluation_engine.temporal.activities.activity")
    @patch("evaluation_engine.temporal.activities.EventPublisher")
    @patch("evaluation_engine.temporal.activities.SandboxClient")
    @patch("evaluation_engine.temporal.activities.Evaluator")
    @patch("evaluation_engine.temporal.activities.EvaluationEngineConfig")
    async def test_closes_resources_on_success(
        self,
        mock_config_cls: MagicMock,
        mock_evaluator_cls: MagicMock,
        mock_sandbox_cls: MagicMock,
        mock_publisher_cls: MagicMock,
        mock_activity: MagicMock,
    ) -> None:
        """Resources (publisher, sandbox) should be closed after evaluation."""
        mock_activity.logger = MagicMock()

        mock_config = MagicMock()
        mock_config.sandbox_base_url = "http://localhost:8002"
        mock_config.architect.redis.url = "redis://localhost:6379"
        mock_config.fail_fast = True
        mock_config_cls.return_value = mock_config

        mock_sandbox = AsyncMock()
        mock_sandbox.close = AsyncMock()
        mock_sandbox_cls.return_value = mock_sandbox

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        mock_evaluator_instance = AsyncMock()
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "task_id": "t",
            "layers": [],
            "overall_verdict": "pass",
        }
        mock_evaluator_instance.evaluate.return_value = mock_report
        mock_evaluator_cls.return_value = mock_evaluator_instance

        await run_evaluation("task-test000001", "sbx-session001")

        mock_publisher.close.assert_awaited_once()
        mock_sandbox.close.assert_awaited_once()

    @patch("evaluation_engine.temporal.activities.activity")
    @patch("evaluation_engine.temporal.activities.EventPublisher")
    @patch("evaluation_engine.temporal.activities.SandboxClient")
    @patch("evaluation_engine.temporal.activities.Evaluator")
    @patch("evaluation_engine.temporal.activities.EvaluationEngineConfig")
    async def test_closes_resources_on_evaluator_error(
        self,
        mock_config_cls: MagicMock,
        mock_evaluator_cls: MagicMock,
        mock_sandbox_cls: MagicMock,
        mock_publisher_cls: MagicMock,
        mock_activity: MagicMock,
    ) -> None:
        """Resources should be closed even when the evaluator raises."""
        mock_activity.logger = MagicMock()

        mock_config = MagicMock()
        mock_config.sandbox_base_url = "http://localhost:8002"
        mock_config.architect.redis.url = "redis://localhost:6379"
        mock_config.fail_fast = True
        mock_config_cls.return_value = mock_config

        mock_sandbox = AsyncMock()
        mock_sandbox.close = AsyncMock()
        mock_sandbox_cls.return_value = mock_sandbox

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        mock_evaluator_instance = AsyncMock()
        mock_evaluator_instance.evaluate.side_effect = RuntimeError("eval boom")
        mock_evaluator_cls.return_value = mock_evaluator_instance

        with pytest.raises(RuntimeError, match="eval boom"):
            await run_evaluation("task-err001", "sbx-err001")

        # Resources must still be cleaned up
        mock_publisher.close.assert_awaited_once()
        mock_sandbox.close.assert_awaited_once()

    @patch("evaluation_engine.temporal.activities.activity")
    @patch("evaluation_engine.temporal.activities.EventPublisher")
    @patch("evaluation_engine.temporal.activities.SandboxClient")
    @patch("evaluation_engine.temporal.activities.Evaluator")
    @patch("evaluation_engine.temporal.activities.EvaluationEngineConfig")
    async def test_connects_event_publisher(
        self,
        mock_config_cls: MagicMock,
        mock_evaluator_cls: MagicMock,
        mock_sandbox_cls: MagicMock,
        mock_publisher_cls: MagicMock,
        mock_activity: MagicMock,
    ) -> None:
        """The event publisher should be connected before evaluation."""
        mock_activity.logger = MagicMock()

        mock_config = MagicMock()
        mock_config.sandbox_base_url = "http://localhost:8002"
        mock_config.architect.redis.url = "redis://localhost:6379"
        mock_config.fail_fast = True
        mock_config_cls.return_value = mock_config

        mock_sandbox = AsyncMock()
        mock_sandbox.close = AsyncMock()
        mock_sandbox_cls.return_value = mock_sandbox

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        mock_evaluator_instance = AsyncMock()
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "task_id": "t",
            "layers": [],
            "overall_verdict": "pass",
        }
        mock_evaluator_instance.evaluate.return_value = mock_report
        mock_evaluator_cls.return_value = mock_evaluator_instance

        await run_evaluation("task-conn001", "sbx-conn001")

        mock_publisher.connect.assert_awaited_once()

    @patch("evaluation_engine.temporal.activities.activity")
    @patch("evaluation_engine.temporal.activities.EventPublisher")
    @patch("evaluation_engine.temporal.activities.SandboxClient")
    @patch("evaluation_engine.temporal.activities.Evaluator")
    @patch("evaluation_engine.temporal.activities.EvaluationEngineConfig")
    async def test_passes_task_id_to_evaluator(
        self,
        mock_config_cls: MagicMock,
        mock_evaluator_cls: MagicMock,
        mock_sandbox_cls: MagicMock,
        mock_publisher_cls: MagicMock,
        mock_activity: MagicMock,
    ) -> None:
        """The evaluator.evaluate call should receive the correct task_id."""
        mock_activity.logger = MagicMock()

        mock_config = MagicMock()
        mock_config.sandbox_base_url = "http://localhost:8002"
        mock_config.architect.redis.url = "redis://localhost:6379"
        mock_config.fail_fast = True
        mock_config_cls.return_value = mock_config

        mock_sandbox = AsyncMock()
        mock_sandbox.close = AsyncMock()
        mock_sandbox_cls.return_value = mock_sandbox

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        mock_evaluator_instance = AsyncMock()
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "task_id": "task-id001",
            "layers": [],
            "overall_verdict": "pass",
        }
        mock_evaluator_instance.evaluate.return_value = mock_report
        mock_evaluator_cls.return_value = mock_evaluator_instance

        await run_evaluation("task-id001", "sbx-id001")

        mock_evaluator_instance.evaluate.assert_awaited_once()
        call_kwargs = mock_evaluator_instance.evaluate.call_args[1]
        assert str(call_kwargs["task_id"]) == "task-id001"
        assert call_kwargs["sandbox_session_id"] == "sbx-id001"
