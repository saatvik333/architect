"""Tests for the IntegrationTestLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.integration_tests import IntegrationTestLayer
from evaluation_engine.models import IntegrationTestResult


class TestIntegrationTestLayer:
    """Tests for :class:`IntegrationTestLayer`."""

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

    @pytest.fixture
    def layer(self, mock_sandbox: AsyncMock) -> IntegrationTestLayer:
        return IntegrationTestLayer(sandbox_client=mock_sandbox)

    def test_layer_name(self, layer: IntegrationTestLayer) -> None:
        assert layer.layer_name == EvalLayer.INTEGRATION_TESTS

    async def test_pass_when_all_tests_pass(
        self,
        layer: IntegrationTestLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """All integration tests pass -> PASS."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest -m integration",
                    exit_code=0,
                    stdout="3 passed in 1.50s",
                    stderr="",
                    duration_ms=1500,
                ),
            ],
            total_duration_ms=1500,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert result.layer == EvalLayer.INTEGRATION_TESTS
        assert isinstance(result.details, IntegrationTestResult)
        assert result.details.passed == 3
        assert result.details.failed == 0

    async def test_fail_soft_when_some_fail(
        self,
        layer: IntegrationTestLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Some integration tests fail -> FAIL_SOFT."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest -m integration",
                    exit_code=1,
                    stdout="FAILED tests/test_api.py::test_endpoint - AssertionError\n2 passed, 1 failed in 2.00s",
                    stderr="",
                    duration_ms=2000,
                ),
            ],
            total_duration_ms=2000,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_SOFT
        assert isinstance(result.details, IntegrationTestResult)
        assert result.details.passed == 2
        assert result.details.failed == 1
        assert len(result.details.failure_details) == 1

    async def test_fail_hard_on_collection_error(
        self,
        layer: IntegrationTestLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Collection error (exit code 2+) -> FAIL_HARD."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest -m integration",
                    exit_code=2,
                    stdout="ERROR collecting tests/test_broken.py",
                    stderr="",
                    duration_ms=500,
                ),
            ],
            total_duration_ms=500,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, IntegrationTestResult)
        assert result.details.errors >= 1

    async def test_pass_when_no_tests_found(
        self,
        layer: IntegrationTestLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """No integration tests collected -> PASS (exit code 0, no summary)."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest -m integration",
                    exit_code=0,
                    stdout="no tests ran in 0.01s",
                    stderr="",
                    duration_ms=10,
                ),
            ],
            total_duration_ms=10,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, IntegrationTestResult)
