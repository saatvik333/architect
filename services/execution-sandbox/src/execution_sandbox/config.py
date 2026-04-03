"""Service-specific configuration for the Execution Sandbox."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from architect_common.config import ArchitectConfig


class ExecutionSandboxConfig(BaseSettings):
    """Configuration knobs specific to the Execution Sandbox service.

    Inherits all infra settings from :class:`ArchitectConfig` and adds
    sandbox-specific tuning parameters.
    """

    model_config = SettingsConfigDict(env_prefix="SANDBOX_")

    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)

    # ── Sandbox-specific settings ─────────────────────────────────────
    default_base_image: str = Field(
        default="architect-sandbox:latest",
        description="Default Docker image for sandbox containers.",
    )
    max_concurrent_sandboxes: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of simultaneously running sandbox containers.",
    )
    workspace_root: str = Field(
        default="/tmp/architect-sandboxes",  # nosec B108 # configurable default for sandbox workspaces
        description="Host directory for temporary workspace mounts.",
    )
    docker_socket: str = Field(
        default="/var/run/docker.sock",
        description="Path to Docker daemon socket.",
    )
    container_user: str = Field(
        default="sandbox",
        description="Non-root user inside sandbox containers.",
    )
    default_timeout_seconds: int = Field(
        default=900,
        ge=30,
        le=3600,
        description="Default execution timeout in seconds.",
    )
    audit_log_max_stdout: int = Field(
        default=50_000,
        ge=1_000,
        description="Maximum characters of stdout to store in audit log entries.",
    )
    audit_log_max_stderr: int = Field(
        default=50_000,
        ge=1_000,
        description="Maximum characters of stderr to store in audit log entries.",
    )
    # ── Executor backend selection ──────────────────────────────────
    executor_backend: str = Field(
        default="docker",
        pattern=r"^(docker|firecracker|auto)$",
        description=(
            "Executor backend: 'docker', 'firecracker', or 'auto'. "
            "'auto' tries Firecracker if KVM is available, falls back to Docker."
        ),
    )

    # ── Firecracker-specific settings ────────────────────────────────
    firecracker_binary: str = Field(
        default="/usr/bin/firecracker",
        description="Path to the Firecracker binary.",
    )
    firecracker_kernel_image: str = Field(
        default="/var/lib/architect/vmlinux",
        description="Path to the kernel image for Firecracker microVMs.",
    )
    firecracker_rootfs_image: str = Field(
        default="/var/lib/architect/rootfs.ext4",
        description="Path to the base rootfs image for Firecracker microVMs.",
    )
    firecracker_jailer_binary: str = Field(
        default="/usr/bin/jailer",
        description="Path to the Firecracker jailer binary.",
    )
    firecracker_socket_dir: str = Field(
        default="/tmp/architect-fc-sockets",  # nosec B108
        description="Directory for Firecracker VM API sockets.",
    )
    firecracker_use_jailer: bool = Field(
        default=False,
        description="Whether to use the jailer for additional isolation.",
    )
    firecracker_ssh_key_path: str = Field(
        default="/var/lib/architect/fc-ssh-key",
        description="Path to the SSH private key for Firecracker VM communication.",
    )
    firecracker_ssh_user: str = Field(
        default="sandbox",
        description="SSH username inside Firecracker VMs.",
    )
    firecracker_ssh_port: int = Field(
        default=22,
        ge=1,
        le=65535,
        description="SSH port inside Firecracker VMs.",
    )

    host: str = "0.0.0.0"  # nosec B104 # intended for container deployments
    port: int = Field(default=8007, ge=1, le=65535)
