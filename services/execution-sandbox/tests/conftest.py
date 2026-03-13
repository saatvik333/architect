"""Shared fixtures for Execution Sandbox tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from architect_common.types import AgentId, TaskId
from execution_sandbox.config import ExecutionSandboxConfig
from execution_sandbox.docker_executor import DockerExecutor
from execution_sandbox.models import (
    NetworkPolicy,
    ResourceLimits,
    SandboxSpec,
)


@pytest.fixture
def sample_resource_limits() -> ResourceLimits:
    return ResourceLimits(cpu_cores=2, memory_mb=4096, disk_mb=10240, timeout_seconds=900)


@pytest.fixture
def sample_network_policy() -> NetworkPolicy:
    return NetworkPolicy(allow_egress=False)


@pytest.fixture
def sample_spec(
    sample_resource_limits: ResourceLimits,
    sample_network_policy: NetworkPolicy,
) -> SandboxSpec:
    return SandboxSpec(
        task_id=TaskId("task-abc123"),
        agent_id=AgentId("agent-xyz789"),
        base_image="architect-sandbox:latest",
        resource_limits=sample_resource_limits,
        network_policy=sample_network_policy,
        environment_vars={"LANG": "en_US.UTF-8"},
    )


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Create a fully mocked ``docker.DockerClient``."""
    client = MagicMock()

    # Mock container returned by containers.run()
    mock_container = MagicMock()
    mock_container.id = "abc123def456"
    mock_container.status = "running"

    # Mock exec_run result
    mock_run_result = MagicMock()
    mock_run_result.exit_code = 0
    mock_run_result.output = (b"hello world\n", b"")
    mock_container.exec_run.return_value = mock_run_result

    # Mock stats
    mock_container.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200_000_000},
            "system_cpu_usage": 10_000_000_000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100_000_000},
            "system_cpu_usage": 9_000_000_000,
        },
        "memory_stats": {
            "usage": 100 * 1024 * 1024,
            "limit": 4096 * 1024 * 1024,
        },
    }

    client.containers.run.return_value = mock_container
    client.containers.get.return_value = mock_container

    return client


@pytest.fixture
def executor(mock_docker_client: MagicMock) -> DockerExecutor:
    """Create a :class:`DockerExecutor` backed by a mocked Docker client."""
    with patch(
        "execution_sandbox.docker_executor.docker.DockerClient", return_value=mock_docker_client
    ):
        ex = DockerExecutor(docker_socket="/var/run/docker.sock")
    return ex


@pytest.fixture
def sandbox_config() -> ExecutionSandboxConfig:
    return ExecutionSandboxConfig()
