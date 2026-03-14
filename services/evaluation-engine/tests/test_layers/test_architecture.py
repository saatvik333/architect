"""Tests for the ArchitectureComplianceLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.architecture import ArchitectureComplianceLayer
from evaluation_engine.models import ArchitectureResult


class TestArchitectureComplianceLayer:
    """Tests for :class:`ArchitectureComplianceLayer`."""

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
    def layer(self, mock_sandbox: AsyncMock) -> ArchitectureComplianceLayer:
        return ArchitectureComplianceLayer(sandbox_client=mock_sandbox)

    def test_layer_name(self, layer: ArchitectureComplianceLayer) -> None:
        assert layer.layer_name == EvalLayer.ARCHITECTURE

    async def test_pass_when_clean(
        self,
        layer: ArchitectureComplianceLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """No violations found -> PASS."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="grep cross-imports",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=50,
                ),
                CommandResult(
                    command="ruff check",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=150,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, ArchitectureResult)
        assert result.details.violations == []
        assert result.details.import_violations == []

    async def test_fail_hard_on_import_violations(
        self,
        layer: ArchitectureComplianceLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Cross-service import violations -> FAIL_HARD."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="grep cross-imports",
                    exit_code=0,
                    stdout="src/my_service/api.py:5:from world_state_ledger import models",
                    stderr="",
                    duration_ms=50,
                ),
                CommandResult(
                    command="ruff check",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=150,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, ArchitectureResult)
        assert len(result.details.import_violations) == 1
        assert result.details.conventions_violated >= 1

    async def test_fail_soft_on_lint_violations_only(
        self,
        layer: ArchitectureComplianceLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Lint violations without import violations -> FAIL_SOFT."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="grep cross-imports",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=50,
                ),
                CommandResult(
                    command="ruff check",
                    exit_code=1,
                    stdout="src/module.py:10:1: F401 'os' imported but unused",
                    stderr="",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=150,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_SOFT
        assert isinstance(result.details, ArchitectureResult)
        assert len(result.details.import_violations) == 0
        assert len(result.details.violations) == 1

    async def test_pass_when_ruff_summary_only(
        self,
        layer: ArchitectureComplianceLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Ruff output is only a 'Found X errors' summary line -> PASS."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="grep cross-imports",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=50,
                ),
                CommandResult(
                    command="ruff check",
                    exit_code=0,
                    stdout="Found 0 errors",
                    stderr="",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=150,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert isinstance(result.details, ArchitectureResult)
        assert result.details.violations == []
