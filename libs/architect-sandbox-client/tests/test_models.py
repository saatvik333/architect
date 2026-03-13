"""Tests for sandbox client models."""

from architect_common.enums import SandboxStatus
from architect_common.types import AgentId, TaskId
from architect_sandbox_client.models import (
    CommandResult,
    ExecutionRequest,
    ExecutionResult,
    ResourceLimitsSpec,
)


def test_resource_limits_defaults() -> None:
    limits = ResourceLimitsSpec()
    assert limits.cpu_cores == 2
    assert limits.memory_mb == 4096
    assert limits.disk_mb == 10240


def test_resource_limits_custom() -> None:
    limits = ResourceLimitsSpec(cpu_cores=4, memory_mb=8192, disk_mb=20480)
    assert limits.cpu_cores == 4
    assert limits.memory_mb == 8192
    assert limits.disk_mb == 20480


def test_execution_request_minimal() -> None:
    req = ExecutionRequest(
        task_id=TaskId("task-abc123def456"),
        agent_id=AgentId("agent-abc123def456"),
    )
    assert req.task_id == "task-abc123def456"
    assert req.agent_id == "agent-abc123def456"
    assert req.files == {}
    assert req.commands == []
    assert req.environment_vars == {}
    assert req.timeout_seconds == 900
    assert req.resource_limits is None


def test_execution_request_full() -> None:
    req = ExecutionRequest(
        task_id=TaskId("task-abc123def456"),
        agent_id=AgentId("agent-abc123def456"),
        files={"main.py": "print('hello')"},
        commands=["python main.py"],
        environment_vars={"PYTHONPATH": "/app"},
        timeout_seconds=300,
        resource_limits=ResourceLimitsSpec(cpu_cores=1, memory_mb=512, disk_mb=2048),
    )
    assert req.files == {"main.py": "print('hello')"}
    assert req.commands == ["python main.py"]
    assert req.timeout_seconds == 300
    assert req.resource_limits is not None
    assert req.resource_limits.cpu_cores == 1


def test_execution_request_is_frozen() -> None:
    req = ExecutionRequest(
        task_id=TaskId("task-abc123def456"),
        agent_id=AgentId("agent-abc123def456"),
    )
    try:
        req.timeout_seconds = 60  # type: ignore[misc]
        raise AssertionError("Should have raised")
    except Exception:
        pass


def test_command_result() -> None:
    result = CommandResult(
        command="python main.py",
        exit_code=0,
        stdout="hello\n",
        stderr="",
        duration_ms=150,
    )
    assert result.exit_code == 0
    assert result.duration_ms == 150


def test_execution_result() -> None:
    cmd = CommandResult(
        command="python main.py",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_ms=100,
    )
    result = ExecutionResult(
        session_id="sess-12345",
        status=SandboxStatus.COMPLETED,
        command_results=[cmd],
        total_duration_ms=200,
        files_modified={"output.txt": "result"},
    )
    assert result.session_id == "sess-12345"
    assert result.status == SandboxStatus.COMPLETED
    assert len(result.command_results) == 1
    assert result.files_modified == {"output.txt": "result"}


def test_execution_result_serialization() -> None:
    cmd = CommandResult(
        command="echo test",
        exit_code=0,
        stdout="test\n",
        stderr="",
        duration_ms=10,
    )
    result = ExecutionResult(
        session_id="sess-99999",
        status=SandboxStatus.COMPLETED,
        command_results=[cmd],
        total_duration_ms=10,
    )
    data = result.model_dump(mode="json")
    assert data["session_id"] == "sess-99999"
    assert data["status"] == "completed"
    assert len(data["command_results"]) == 1

    # Round-trip
    restored = ExecutionResult.model_validate(data)
    assert restored == result
