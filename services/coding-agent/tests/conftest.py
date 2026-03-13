"""Shared pytest fixtures for coding-agent tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock

import pytest

from architect_common.enums import SandboxStatus
from architect_events.publisher import EventPublisher
from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse, TokenUsage
from architect_sandbox_client.client import SandboxClient
from architect_sandbox_client.models import CommandResult, ExecutionResult
from coding_agent.agent import CodingAgentLoop
from coding_agent.models import (
    AgentConfig,
    AgentRun,
    CodebaseContext,
    SpecContext,
)


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Return a mock LLMClient that returns canned code output."""
    client = AsyncMock(spec=LLMClient)

    # Default response: a simple Python file
    client.generate.return_value = LLMResponse(
        content=(
            "Here is the implementation:\n"
            "\n"
            "```python\n"
            "# src/hello.py\n"
            "def greet(name: str) -> str:\n"
            '    return f"Hello, {name}!"\n'
            "```\n"
            "\n"
            "```python\n"
            "# tests/test_hello.py\n"
            "from src.hello import greet\n"
            "\n"
            "def test_greet() -> None:\n"
            '    assert greet("World") == "Hello, World!"\n'
            "```\n"
        ),
        model_id="claude-sonnet-4-20250514",
        input_tokens=500,
        output_tokens=200,
        stop_reason="end_turn",
    )

    # Mock the total_usage property
    type(client).total_usage = PropertyMock(
        return_value=TokenUsage(
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            estimated_cost_usd=0.01,
        )
    )

    return client


@pytest.fixture
def mock_sandbox_client() -> AsyncMock:
    """Return a mock SandboxClient that returns successful execution results."""
    client = AsyncMock(spec=SandboxClient)

    # Default: all commands succeed
    client.execute.return_value = ExecutionResult(
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
            CommandResult(
                command="pytest",
                exit_code=0,
                stdout="3 passed in 0.5s",
                stderr="",
                duration_ms=500,
            ),
        ],
        total_duration_ms=550,
    )

    return client


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Return a mock EventPublisher that records publish calls."""
    publisher = AsyncMock(spec=EventPublisher)
    publisher.publish.return_value = "mock-mid-001"
    return publisher


@pytest.fixture
def sample_spec() -> SpecContext:
    """Return a sample task specification."""
    return SpecContext(
        spec_hash="a" * 64,
        title="Add greeting function",
        description="Implement a greeting function that takes a name and returns a greeting.",
        acceptance_criteria=[
            "Function returns 'Hello, <name>!'",
            "Unit tests pass",
        ],
        constraints=["No external dependencies"],
    )


@pytest.fixture
def sample_codebase() -> CodebaseContext:
    """Return a sample codebase context."""
    return CodebaseContext(
        commit_hash="b" * 40,
        relevant_files=["src/__init__.py"],
        file_contents={"src/__init__.py": ""},
        total_tokens_estimate=100,
    )


@pytest.fixture
def sample_agent_run(
    sample_spec: SpecContext,
    sample_codebase: CodebaseContext,
) -> AgentRun:
    """Return a sample agent run."""
    return AgentRun(
        task_id="task-test000001",
        config=AgentConfig(),
        spec_context=sample_spec,
        codebase_context=sample_codebase,
    )


@pytest.fixture
def agent_loop(
    mock_llm_client: AsyncMock,
    mock_sandbox_client: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> CodingAgentLoop:
    """Return a CodingAgentLoop wired with mock dependencies."""
    return CodingAgentLoop(
        llm_client=mock_llm_client,
        sandbox_client=mock_sandbox_client,
        event_publisher=mock_event_publisher,
    )
