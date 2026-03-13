"""Tests for the CompilationLayer."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import EvalLayer, EvalVerdict, SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.layers.compilation import CompilationLayer
from evaluation_engine.models import CompilationResult


class TestCompilationLayer:
    """Tests for :class:`CompilationLayer`."""

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
    def layer(self, mock_sandbox: AsyncMock) -> CompilationLayer:
        return CompilationLayer(sandbox_client=mock_sandbox)

    def test_layer_name(self, layer: CompilationLayer) -> None:
        assert layer.layer_name == EvalLayer.COMPILATION

    async def test_pass_when_no_errors(
        self,
        layer: CompilationLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """All files compile cleanly -> PASS."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="py_compile",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.PASS
        assert result.layer == EvalLayer.COMPILATION
        assert isinstance(result.details, CompilationResult)
        assert result.details.success is True
        assert result.details.errors == []

    async def test_fail_hard_on_syntax_error(
        self,
        layer: CompilationLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Syntax errors in any file -> FAIL_HARD."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="py_compile",
                    exit_code=1,
                    stdout="",
                    stderr="SyntaxError: invalid syntax (bad_file.py, line 5)",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        assert isinstance(result.details, CompilationResult)
        assert result.details.success is False
        assert len(result.details.errors) > 0
        assert "SyntaxError" in result.details.errors[0]

    async def test_warnings_collected(
        self,
        layer: CompilationLayer,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Warnings are collected separately from errors."""
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="py_compile",
                    exit_code=1,
                    stdout="",
                    stderr="SyntaxError: bad syntax\nDeprecationWarning: old feature",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )

        result = await layer.evaluate("sbx-test000001")

        assert result.verdict == EvalVerdict.FAIL_HARD
        details = result.details
        assert isinstance(details, CompilationResult)
        assert len(details.errors) >= 1
        assert len(details.warnings) >= 1
