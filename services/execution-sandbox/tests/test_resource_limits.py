"""Tests for container config generation and resource usage checking."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from architect_common.types import AgentId, TaskId
from execution_sandbox.models import (
    NetworkPolicy,
    ResourceLimits,
    SandboxSpec,
)
from execution_sandbox.resource_limits import check_resource_usage, create_container_config


class TestCreateContainerConfig:
    """Tests for :func:`create_container_config`."""

    def test_default_spec_produces_valid_config(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)

        assert config["image"] == "architect-sandbox:latest"
        assert config["detach"] is True
        assert config["read_only"] is True
        assert config["user"] == "1000:1000"
        assert config["working_dir"] == "/workspace"
        assert "no-new-privileges" in config["security_opt"]

    def test_cpu_limit_as_nanocpus(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        expected_nano = int(2 * 1e9)
        assert config["nano_cpus"] == expected_nano

    def test_memory_limit_formatted(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        assert config["mem_limit"] == "4096m"
        # Swap should equal mem (swap disabled)
        assert config["memswap_limit"] == "4096m"

    def test_network_none_when_egress_disabled(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        assert config["network_mode"] == "none"

    def test_network_bridge_when_egress_enabled(self) -> None:
        spec = SandboxSpec(
            task_id=TaskId("task-1"),
            agent_id=AgentId("agent-1"),
            network_policy=NetworkPolicy(allow_egress=True),
        )
        config = create_container_config(spec)
        assert config["network_mode"] == "bridge"

    def test_tmpfs_mounts_present(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        assert "/tmp" in config["tmpfs"]  # nosec B108
        assert "/workspace" in config["tmpfs"]

    def test_environment_includes_task_and_agent(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        env = config["environment"]
        assert env["SANDBOX_TASK_ID"] == "task-abc123"
        assert env["SANDBOX_AGENT_ID"] == "agent-xyz789"
        # User-supplied env var should also be present
        assert env["LANG"] == "en_US.UTF-8"

    def test_labels_set(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        labels = config["labels"]
        assert labels["architect.task_id"] == "task-abc123"
        assert labels["architect.component"] == "execution-sandbox"

    def test_command_is_sleep(self, sample_spec: SandboxSpec) -> None:
        config = create_container_config(sample_spec)
        assert config["command"] == ["sleep", "900"]

    def test_pids_limit_present(self, sample_spec: SandboxSpec) -> None:
        """Fork-bomb prevention: pids_limit must be set."""
        config = create_container_config(sample_spec)
        assert config["pids_limit"] == 256

    def test_blkio_weight_present(self, sample_spec: SandboxSpec) -> None:
        """Low I/O priority: blkio_weight must be set."""
        config = create_container_config(sample_spec)
        assert config["blkio_weight"] == 100

    def test_cap_drop_all(self, sample_spec: SandboxSpec) -> None:
        """All Linux capabilities must be dropped."""
        config = create_container_config(sample_spec)
        assert config["cap_drop"] == ["ALL"]

    def test_cap_add_minimal(self, sample_spec: SandboxSpec) -> None:
        """Only the minimal required capabilities are added back."""
        config = create_container_config(sample_spec)
        expected = ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"]
        assert config["cap_add"] == expected

    def test_seccomp_profile_in_security_opt(self, sample_spec: SandboxSpec) -> None:
        """The seccomp profile path must be present in security_opt."""
        config = create_container_config(sample_spec)
        security_opts = config["security_opt"]
        seccomp_entries = [s for s in security_opts if "seccomp=" in s]
        assert len(seccomp_entries) == 1
        assert "sandbox-profile.json" in seccomp_entries[0]

    def test_custom_resource_limits(self) -> None:
        spec = SandboxSpec(
            task_id=TaskId("task-custom"),
            agent_id=AgentId("agent-custom"),
            resource_limits=ResourceLimits(
                cpu_cores=4, memory_mb=8192, disk_mb=20480, timeout_seconds=1800
            ),
        )
        config = create_container_config(spec)
        assert config["nano_cpus"] == int(4 * 1e9)
        assert config["mem_limit"] == "8192m"
        assert config["command"] == ["sleep", "1800"]


class TestCheckResourceUsage:
    """Tests for :func:`check_resource_usage`."""

    def test_normal_stats(self) -> None:
        container = MagicMock()
        container.stats.return_value = {
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
                "usage": 512 * 1024 * 1024,
                "limit": 4096 * 1024 * 1024,
            },
        }

        usage = check_resource_usage(container)

        assert usage["cpu_percent"] > 0
        assert usage["memory_used_mb"] == pytest.approx(512.0, abs=0.1)
        assert usage["memory_limit_mb"] == pytest.approx(4096.0, abs=0.1)

    def test_zero_system_delta(self) -> None:
        """When system_delta is zero, cpu_percent should be 0."""
        container = MagicMock()
        container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 1000,
                "online_cpus": 1,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 1000,
            },
            "memory_stats": {"usage": 0, "limit": 0},
        }

        usage = check_resource_usage(container)
        assert usage["cpu_percent"] == 0.0

    def test_stats_exception_returns_zeroes(self) -> None:
        """When stats() raises, all values should be zero."""
        container = MagicMock()
        container.stats.side_effect = RuntimeError("container not running")

        usage = check_resource_usage(container)
        assert usage == {
            "cpu_percent": 0.0,
            "memory_used_mb": 0.0,
            "memory_limit_mb": 0.0,
        }
