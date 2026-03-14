"""Tests for the AdversarialLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_llm.models import LLMResponse
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.adversarial import AdversarialLayer
from evaluation_engine.models import AdversarialResult


class TestAdversarialLayer:
    """Tests for :class:`AdversarialLayer`."""

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
    def mock_llm(self) -> AsyncMock:
        """Return a mock LLMClient."""
        client = AsyncMock()
        client.generate.return_value = LLMResponse(
            content="def test_adversarial(): pass",
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )
        return client

    @pytest.fixture
    def layer(self, mock_sandbox: AsyncMock, mock_llm: AsyncMock) -> AdversarialLayer:
        return AdversarialLayer(sandbox_client=mock_sandbox, llm_client=mock_llm)

    def test_layer_name(self, layer: AdversarialLayer) -> None:
        assert layer.layer_name == EvalLayer.ADVERSARIAL

    async def test_pass_when_no_vulnerabilities(
        self,
        layer: AdversarialLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """No vulnerabilities found -> PASS."""
        # First call: read source code
        source_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="cat",
                    exit_code=0,
                    stdout="def hello(): return 'world'",
                    stderr="",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )
        # Second call: run adversarial tests (all pass)
        test_result = ExecutionResult(
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
        mock_sandbox.execute.side_effect = [source_result, test_result]

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, AdversarialResult)
        assert result.details.vulnerabilities_found == 0
        assert result.details.severity == "none"

    async def test_fail_soft_on_low_severity(
        self,
        layer: AdversarialLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Low severity findings -> FAIL_SOFT."""
        source_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="cat",
                    exit_code=0,
                    stdout="def hello(): return 'world'",
                    stderr="",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )
        test_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=1,
                    stdout="FAILED test_adversarial_generated.py::test_null_input\n1 passed, 1 failed in 0.50s",
                    stderr="",
                    duration_ms=500,
                ),
            ],
            total_duration_ms=500,
        )
        mock_sandbox.execute.side_effect = [source_result, test_result]

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_SOFT
        assert isinstance(result.details, AdversarialResult)
        assert result.details.vulnerabilities_found == 1
        assert result.details.severity == "low"

    async def test_fail_hard_on_critical_severity(
        self,
        layer: AdversarialLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Critical severity (many vulnerabilities) -> FAIL_HARD."""
        source_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="cat",
                    exit_code=0,
                    stdout="def hello(): return 'world'",
                    stderr="",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )
        # 11 failures -> critical
        failures = "\n".join(
            f"FAILED test_adversarial_generated.py::test_vuln_{i}" for i in range(11)
        )
        test_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=1,
                    stdout=f"{failures}\n11 failed in 1.00s",
                    stderr="",
                    duration_ms=1000,
                ),
            ],
            total_duration_ms=1000,
        )
        mock_sandbox.execute.side_effect = [source_result, test_result]

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, AdversarialResult)
        assert result.details.vulnerabilities_found == 11
        assert result.details.severity == "critical"

    async def test_fail_hard_on_llm_error(
        self,
        layer: AdversarialLayer,
        mock_sandbox: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """LLM generation error -> FAIL_HARD."""
        source_result = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="cat",
                    exit_code=0,
                    stdout="def hello(): return 'world'",
                    stderr="",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )
        mock_sandbox.execute.side_effect = [source_result]
        mock_llm.generate.side_effect = RuntimeError("LLM unavailable")

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, AdversarialResult)
