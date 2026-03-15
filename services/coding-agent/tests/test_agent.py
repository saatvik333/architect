"""Tests for the CodingAgentLoop."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from architect_common.enums import SandboxStatus
from architect_sandbox_client.models import CommandResult, ExecutionResult
from coding_agent.agent import CodingAgentLoop
from coding_agent.models import AgentOutput, AgentRun


@pytest.fixture(autouse=True)
def _mock_git_committer():
    """Prevent agent tests from writing files to the real working directory.

    The default AgentRun.repo_path is "." (CWD), and GitCommitter.commit()
    writes files to disk before attempting git operations.  Mocking it avoids
    side-effects on the project tree.
    """
    with patch("coding_agent.agent.GitCommitter") as mock_cls:
        mock_cls.return_value.commit = AsyncMock(return_value="a" * 40)
        yield mock_cls


class TestCodingAgentLoop:
    """Tests for :class:`CodingAgentLoop`."""

    async def test_successful_execution(
        self,
        agent_loop: CodingAgentLoop,
        sample_agent_run: AgentRun,
    ) -> None:
        """Agent produces output with files when sandbox passes."""
        output = await agent_loop.execute(sample_agent_run)

        assert isinstance(output, AgentOutput)
        assert output.task_id == sample_agent_run.task_id
        assert output.agent_id == sample_agent_run.id
        assert len(output.files) > 0
        assert output.commit_message != ""
        assert output.tokens_used > 0

    async def test_files_include_tests(
        self,
        agent_loop: CodingAgentLoop,
        sample_agent_run: AgentRun,
    ) -> None:
        """Agent output includes test files detected by path."""
        output = await agent_loop.execute(sample_agent_run)

        test_files = [f for f in output.files if f.is_test]
        src_files = [f for f in output.files if not f.is_test]

        assert len(test_files) >= 1
        assert len(src_files) >= 1

    async def test_retries_on_failure(
        self,
        mock_llm_client: AsyncMock,
        mock_sandbox_client: AsyncMock,
        mock_event_publisher: AsyncMock,
        sample_agent_run: AgentRun,
    ) -> None:
        """Agent retries code generation when sandbox execution fails."""
        # First call fails, second succeeds
        mock_sandbox_client.execute.side_effect = [
            ExecutionResult(
                session_id="sbx-test000001",
                status=SandboxStatus.COMPLETED,
                command_results=[
                    CommandResult(
                        command="pytest",
                        exit_code=1,
                        stdout="1 failed in 0.3s",
                        stderr="FAILED tests/test_hello.py::test_greet - AssertionError",
                        duration_ms=300,
                    ),
                ],
                total_duration_ms=300,
            ),
            ExecutionResult(
                session_id="sbx-test000001",
                status=SandboxStatus.COMPLETED,
                command_results=[
                    CommandResult(
                        command="pytest",
                        exit_code=0,
                        stdout="1 passed in 0.3s",
                        stderr="",
                        duration_ms=300,
                    ),
                ],
                total_duration_ms=300,
            ),
        ]

        loop = CodingAgentLoop(
            llm_client=mock_llm_client,
            sandbox_client=mock_sandbox_client,
            event_publisher=mock_event_publisher,
            max_retries=3,
        )

        output = await loop.execute(sample_agent_run)

        assert isinstance(output, AgentOutput)
        # fix_errors should have been called once
        assert mock_llm_client.generate.call_count >= 2

    async def test_event_published_on_completion(
        self,
        agent_loop: CodingAgentLoop,
        sample_agent_run: AgentRun,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """An agent.completed event is published when the loop finishes."""
        await agent_loop.execute(sample_agent_run)

        assert mock_event_publisher.publish.called
        call_args = mock_event_publisher.publish.call_args
        envelope = call_args[0][0]
        assert envelope.type == "agent.completed"


class TestCollectErrors:
    """Tests for the static _collect_errors helper."""

    def test_no_errors_on_success(self) -> None:
        result = ExecutionResult(
            session_id="sbx-test",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=0,
                    stdout="3 passed",
                    stderr="",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=100,
        )
        errors = CodingAgentLoop._collect_errors(result)
        assert errors == []

    def test_collects_error_lines(self) -> None:
        result = ExecutionResult(
            session_id="sbx-test",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=1,
                    stdout="",
                    stderr="FAILED tests/test_x.py::test_y - AssertionError",
                    duration_ms=100,
                ),
            ],
            total_duration_ms=100,
        )
        errors = CodingAgentLoop._collect_errors(result)
        assert len(errors) >= 1
        assert "FAILED" in errors[0]
