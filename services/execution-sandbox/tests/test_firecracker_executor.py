"""Tests for the Firecracker executor and KVM availability check."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from execution_sandbox.config import ExecutionSandboxConfig
from execution_sandbox.kvm_check import is_firecracker_available, is_kvm_available

# ── KVM check tests ──────────────────────────────────────────────────


class TestKvmCheck:
    def test_kvm_not_found(self) -> None:
        with patch("os.path.exists", return_value=False):
            assert is_kvm_available() is False

    def test_kvm_not_char_device(self) -> None:
        mock_stat = MagicMock()
        mock_stat.st_mode = 0o100644  # regular file
        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=mock_stat),
        ):
            assert is_kvm_available() is False

    def test_kvm_no_permission(self) -> None:
        import stat

        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFCHR | 0o666
        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=mock_stat_result),
            patch("os.access", return_value=False),
        ):
            assert is_kvm_available() is False

    def test_kvm_available(self) -> None:
        import stat

        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFCHR | 0o666
        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=mock_stat_result),
            patch("os.access", return_value=True),
        ):
            assert is_kvm_available() is True

    def test_kvm_os_error(self) -> None:
        with patch("os.path.exists", side_effect=OSError("test")):
            assert is_kvm_available() is False


class TestFirecrackerAvailable:
    def test_binary_exists_and_executable(self) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
        ):
            assert is_firecracker_available("/usr/bin/firecracker") is True

    def test_binary_not_found(self) -> None:
        with patch("os.path.isfile", return_value=False):
            assert is_firecracker_available("/usr/bin/firecracker") is False

    def test_binary_not_executable(self) -> None:
        with (
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=False),
        ):
            assert is_firecracker_available("/usr/bin/firecracker") is False


# ── Executor factory tests ───────────────────────────────────────────


class TestExecutorFactory:
    def test_docker_backend(self) -> None:
        from execution_sandbox.api.dependencies import _create_executor
        from execution_sandbox.docker_executor import DockerExecutor

        config = ExecutionSandboxConfig(executor_backend="docker")
        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = _create_executor(config)
        assert isinstance(executor, DockerExecutor)

    def test_auto_backend_no_kvm(self) -> None:
        from execution_sandbox.api.dependencies import _create_executor
        from execution_sandbox.docker_executor import DockerExecutor

        config = ExecutionSandboxConfig(executor_backend="auto")
        with (
            patch("execution_sandbox.kvm_check.is_kvm_available", return_value=False),
            patch("execution_sandbox.docker_executor.docker.DockerClient"),
        ):
            executor = _create_executor(config)
        assert isinstance(executor, DockerExecutor)

    def test_auto_backend_with_kvm(self) -> None:
        from execution_sandbox.api.dependencies import _create_executor
        from execution_sandbox.firecracker_executor import FirecrackerExecutor

        config = ExecutionSandboxConfig(executor_backend="auto")
        with (
            patch("execution_sandbox.kvm_check.is_kvm_available", return_value=True),
            patch("execution_sandbox.kvm_check.is_firecracker_available", return_value=True),
        ):
            executor = _create_executor(config)
        assert isinstance(executor, FirecrackerExecutor)

    def test_firecracker_backend(self) -> None:
        from execution_sandbox.api.dependencies import _create_executor
        from execution_sandbox.firecracker_executor import FirecrackerExecutor

        config = ExecutionSandboxConfig(executor_backend="firecracker")
        executor = _create_executor(config)
        assert isinstance(executor, FirecrackerExecutor)


# ── Config tests ─────────────────────────────────────────────────────


class TestFirecrackerConfig:
    def test_default_config(self) -> None:
        config = ExecutionSandboxConfig()
        assert config.executor_backend == "docker"
        assert config.firecracker_binary == "/usr/bin/firecracker"
        assert config.firecracker_use_jailer is False

    def test_firecracker_config(self) -> None:
        config = ExecutionSandboxConfig(
            executor_backend="firecracker",
            firecracker_binary="/opt/fc/firecracker",
            firecracker_use_jailer=True,
        )
        assert config.executor_backend == "firecracker"
        assert config.firecracker_binary == "/opt/fc/firecracker"
        assert config.firecracker_use_jailer is True

    def test_invalid_backend_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExecutionSandboxConfig(executor_backend="invalid")


# ── Model tests ──────────────────────────────────────────────────────


class TestSandboxSessionExecutorType:
    def test_default_executor_type(self) -> None:
        from execution_sandbox.models import SandboxSession, SandboxSpec

        spec = SandboxSpec(task_id="task-abc", agent_id="agent-xyz")
        session = SandboxSession(spec=spec)
        assert session.executor_type == "docker"

    def test_firecracker_executor_type(self) -> None:
        from execution_sandbox.models import SandboxSession, SandboxSpec

        spec = SandboxSpec(task_id="task-abc", agent_id="agent-xyz")
        session = SandboxSession(spec=spec, executor_type="firecracker")
        assert session.executor_type == "firecracker"
