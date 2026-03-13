"""Shared pytest fixtures for evaluation-engine tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from architect_common.enums import SandboxStatus
from architect_events.publisher import EventPublisher
from architect_sandbox_client.client import SandboxClient
from architect_sandbox_client.models import CommandResult, ExecutionResult
from evaluation_engine.evaluator import Evaluator


@pytest.fixture
def mock_sandbox_client() -> AsyncMock:
    """Return a mock SandboxClient that returns successful execution results."""
    client = AsyncMock(spec=SandboxClient)

    # Default: get_session returns basic info
    client.get_session.return_value = {
        "id": "sbx-test000001",
        "task_id": "task-test000001",
        "agent_id": "agent-test000001",
        "status": SandboxStatus.READY,
    }

    # Default: execute returns a successful result with no output
    client.execute.return_value = ExecutionResult(
        session_id="sbx-test000001",
        status=SandboxStatus.COMPLETED,
        command_results=[
            CommandResult(
                command="echo ok",
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=100,
            ),
        ],
        total_duration_ms=100,
    )

    return client


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Return a mock EventPublisher that records publish calls."""
    publisher = AsyncMock(spec=EventPublisher)
    publisher.publish.return_value = "mock-mid-001"
    return publisher


@pytest.fixture
def evaluator(
    mock_sandbox_client: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> Evaluator:
    """Return an Evaluator wired with mock dependencies."""
    return Evaluator(
        sandbox_client=mock_sandbox_client,
        event_publisher=mock_event_publisher,
    )


def make_execution_result(
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    command: str = "test-cmd",
) -> ExecutionResult:
    """Helper to build an ExecutionResult with a single command."""
    return ExecutionResult(
        session_id="sbx-test000001",
        status=SandboxStatus.COMPLETED,
        command_results=[
            CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=100,
            ),
        ],
        total_duration_ms=100,
    )
