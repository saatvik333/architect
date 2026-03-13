"""Translate SandboxSpec into Docker container configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from execution_sandbox.models import SandboxSpec

# Path to the seccomp profile mounted on the Docker host
SECCOMP_PROFILE_PATH = Path("/etc/docker/seccomp/sandbox-profile.json")


def create_container_config(spec: SandboxSpec) -> dict[str, Any]:
    """Build the ``docker.containers.run()`` kwargs from a :class:`SandboxSpec`.

    The returned dict is suitable for passing as ``**kwargs`` to
    ``docker.DockerClient.containers.run()``.
    """
    limits = spec.resource_limits
    network = spec.network_policy

    # CPU: Docker expects nano_cpus (1 core = 1e9 nanocpus)
    nano_cpus = int(limits.cpu_cores * 1e9)

    # Memory: Docker expects bytes
    mem_limit = f"{limits.memory_mb}m"

    # Network mode
    network_mode = "none" if not network.allow_egress else "bridge"

    # Tmpfs mounts for writable areas on a read-only rootfs
    tmpfs = {
        "/tmp": f"size={limits.disk_mb}m,mode=1777",
        "/workspace": f"size={limits.disk_mb}m,mode=1777",
    }

    # Environment variables
    environment = {
        "SANDBOX_TASK_ID": spec.task_id,
        "SANDBOX_AGENT_ID": spec.agent_id,
        **spec.environment_vars,
    }

    config: dict[str, Any] = {
        "image": spec.base_image,
        "nano_cpus": nano_cpus,
        "mem_limit": mem_limit,
        "memswap_limit": mem_limit,  # disable swap
        "pids_limit": 256,  # hard cap to prevent fork bombs
        "blkio_weight": 100,  # low I/O priority so sandbox cannot starve host
        "network_mode": network_mode,
        "read_only": True,
        "tmpfs": tmpfs,
        "cap_drop": ["ALL"],
        "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"],
        "security_opt": [
            "no-new-privileges",
            f"seccomp={SECCOMP_PROFILE_PATH}",
        ],
        "user": "1000:1000",
        "working_dir": "/workspace",
        "environment": environment,
        "stdin_open": False,
        "tty": False,
        "detach": True,
        "labels": {
            "architect.task_id": spec.task_id,
            "architect.agent_id": spec.agent_id,
            "architect.component": "execution-sandbox",
        },
        # Keep the container running so we can exec into it
        "command": ["sleep", str(limits.timeout_seconds)],
    }

    return config


def check_resource_usage(container: Any) -> dict[str, float]:
    """Read resource consumption stats from a running Docker container.

    Args:
        container: A ``docker.models.containers.Container`` instance.

    Returns:
        A dict with keys ``cpu_percent``, ``memory_used_mb``, ``memory_limit_mb``.
    """
    try:
        stats = container.stats(stream=False)
    except Exception:
        return {
            "cpu_percent": 0.0,
            "memory_used_mb": 0.0,
            "memory_limit_mb": 0.0,
        }

    # ── CPU calculation ──────────────────────────────────────────
    cpu_delta = (
        stats["cpu_stats"]["cpu_usage"]["total_usage"]
        - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = (
        stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
    )
    num_cpus = stats["cpu_stats"].get("online_cpus", 1)

    cpu_percent = 0.0
    if system_delta > 0 and cpu_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

    # ── Memory calculation ───────────────────────────────────────
    memory_stats = stats.get("memory_stats", {})
    memory_used_mb = memory_stats.get("usage", 0) / (1024 * 1024)
    memory_limit_mb = memory_stats.get("limit", 0) / (1024 * 1024)

    return {
        "cpu_percent": round(cpu_percent, 2),
        "memory_used_mb": round(memory_used_mb, 2),
        "memory_limit_mb": round(memory_limit_mb, 2),
    }
