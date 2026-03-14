"""Tests for the SpecComplianceLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.spec_compliance import SpecComplianceLayer
from evaluation_engine.models import SpecComplianceResult


class TestSpecComplianceLayer:
    """Tests for :class:`SpecComplianceLayer`."""

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
        layer = SpecComplianceLayer(sandbox_client=mock_sandbox)
        assert layer.layer_name == EvalLayer.SPEC_COMPLIANCE

    async def test_pass_when_all_criteria_met(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """All acceptance criteria have matching tests -> PASS."""
        layer = SpecComplianceLayer(
            sandbox_client=mock_sandbox,
            acceptance_criteria=["user can login", "user can logout"],
        )
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest --collect-only -q",
                    exit_code=0,
                    stdout=(
                        "tests/test_auth.py::test_user_can_login\n"
                        "tests/test_auth.py::test_user_can_logout\n"
                        "\n2 tests collected"
                    ),
                    stderr="",
                    duration_ms=200,
                ),
            ],
            total_duration_ms=200,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, SpecComplianceResult)
        assert result.details.criteria_total == 2
        assert result.details.criteria_met == 2
        assert result.details.criteria_unmet == []
        assert result.details.compliance_score == 1.0

    async def test_fail_soft_when_partial_criteria_met(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """>=50% of criteria met -> FAIL_SOFT."""
        layer = SpecComplianceLayer(
            sandbox_client=mock_sandbox,
            acceptance_criteria=["user can login", "user can logout"],
        )
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest --collect-only -q",
                    exit_code=0,
                    stdout=(
                        "tests/test_auth.py::test_user_can_login\n"
                        "\n1 test collected"
                    ),
                    stderr="",
                    duration_ms=200,
                ),
            ],
            total_duration_ms=200,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_SOFT
        assert isinstance(result.details, SpecComplianceResult)
        assert result.details.criteria_met == 1
        assert result.details.compliance_score == 0.5

    async def test_fail_hard_when_none_met(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """<50% of criteria met -> FAIL_HARD."""
        layer = SpecComplianceLayer(
            sandbox_client=mock_sandbox,
            acceptance_criteria=["user can login", "user can logout", "dashboard loads"],
        )
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest --collect-only -q",
                    exit_code=0,
                    stdout="no tests ran in 0.01s",
                    stderr="",
                    duration_ms=10,
                ),
            ],
            total_duration_ms=10,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, SpecComplianceResult)
        assert result.details.criteria_met == 0
        assert result.details.compliance_score == 0.0

    async def test_pass_when_empty_criteria(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """No acceptance criteria provided -> trivially PASS."""
        layer = SpecComplianceLayer(sandbox_client=mock_sandbox)

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, SpecComplianceResult)
        assert result.details.criteria_total == 0
