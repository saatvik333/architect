"""Tests for the RegressionLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.regression import RegressionLayer
from evaluation_engine.models import RegressionResult


class TestRegressionLayer:
    """Tests for :class:`RegressionLayer`."""

    @pytest.fixture
    def mock_sandbox(self) -> AsyncMock:
        """Return a mock SandboxClient."""
        client = AsyncMock()
        client.get_session.return_value = {
            "id": "sbx-test000001",
            "task_id": "task-test000001",
            "agent_id": "agent-test000001",
            "status": SandboxStatus.READY,
        }
        return client

    def test_layer_name(self, mock_sandbox: AsyncMock) -> None:
        layer = RegressionLayer(sandbox_client=mock_sandbox)
        assert layer.layer_name == EvalLayer.REGRESSION

    async def test_pass_when_all_pass_and_count_matches(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """All tests pass and count >= baseline -> PASS."""
        layer = RegressionLayer(sandbox_client=mock_sandbox, baseline_test_count=5)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=0,
                    stdout="5 passed in 1.00s",
                    stderr="",
                    duration_ms=1000,
                ),
            ],
            total_duration_ms=1000,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, RegressionResult)
        assert result.details.regressions_found == 0
        assert result.details.baseline_test_count == 5

    async def test_fail_hard_on_regressions(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Test failures (regressions) -> FAIL_HARD."""
        layer = RegressionLayer(sandbox_client=mock_sandbox, baseline_test_count=5)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=1,
                    stdout="FAILED tests/test_core.py::test_something\n3 passed, 2 failed in 1.50s",
                    stderr="",
                    duration_ms=1500,
                ),
            ],
            total_duration_ms=1500,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, RegressionResult)
        assert result.details.regressions_found == 2
        assert len(result.details.regression_details) == 1

    async def test_fail_soft_when_count_dropped(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """All pass but count dropped below baseline -> FAIL_SOFT."""
        layer = RegressionLayer(sandbox_client=mock_sandbox, baseline_test_count=10)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=0,
                    stdout="7 passed in 0.80s",
                    stderr="",
                    duration_ms=800,
                ),
            ],
            total_duration_ms=800,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_SOFT
        assert isinstance(result.details, RegressionResult)
        assert result.details.regressions_found == 0
        assert result.details.baseline_test_count == 10

    async def test_pass_with_empty_baseline(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Baseline is 0 (default) and all pass -> PASS."""
        layer = RegressionLayer(sandbox_client=mock_sandbox)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=0,
                    stdout="3 passed in 0.50s",
                    stderr="",
                    duration_ms=500,
                ),
            ],
            total_duration_ms=500,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, RegressionResult)
        assert result.details.baseline_test_count == 0
