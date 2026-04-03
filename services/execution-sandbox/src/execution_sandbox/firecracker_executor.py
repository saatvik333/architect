"""Firecracker microVM-backed sandbox executor.

Provides hard isolation via Firecracker microVMs instead of Docker containers.
Requires KVM support on the host. Falls back to Docker when KVM is unavailable
(controlled via the ``executor_backend`` config option).

Communication with VMs uses SSH (simplest for MVP). A future enhancement may
use virtio-vsock for lower latency.
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import SandboxStatus
from architect_common.errors import SandboxError, SandboxSecurityError, SandboxTimeoutError
from architect_common.logging import get_logger
from architect_common.types import utcnow
from execution_sandbox.config import ExecutionSandboxConfig
from execution_sandbox.executor_base import ExecutorBase
from execution_sandbox.models import (
    AuditLogEntry,
    SandboxSession,
    SandboxSpec,
    SessionTimestamps,
)
from execution_sandbox.security import validate_command, validate_files

logger = get_logger(component="firecracker_executor")


class _VMHandle:
    """Internal state for a running Firecracker microVM."""

    __slots__ = ("ip_address", "process", "rootfs_path", "socket_path", "vm_id")

    def __init__(
        self,
        vm_id: str,
        socket_path: Path,
        rootfs_path: Path,
        process: asyncio.subprocess.Process | None = None,
        ip_address: str = "",
    ) -> None:
        self.vm_id = vm_id
        self.socket_path = socket_path
        self.rootfs_path = rootfs_path
        self.process = process
        self.ip_address = ip_address


class FirecrackerExecutor(ExecutorBase):
    """Runs sandboxed code inside Firecracker microVMs.

    Each :class:`SandboxSession` maps to exactly one microVM.
    """

    def __init__(
        self,
        config: ExecutionSandboxConfig,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._config = config
        self._sessions: dict[str, SandboxSession] = {}
        self._vms: dict[str, _VMHandle] = {}
        self._session_factory = session_factory
        self._socket_dir = Path(config.firecracker_socket_dir)
        self._socket_dir.mkdir(parents=True, exist_ok=True)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def create(self, spec: SandboxSpec) -> SandboxSession:
        """Provision a Firecracker microVM from *spec*."""
        vm_id = f"fc-{uuid.uuid4().hex[:12]}"
        socket_path = self._socket_dir / f"{vm_id}.sock"
        rootfs_path = self._socket_dir / f"{vm_id}.ext4"

        session = SandboxSession(
            spec=spec,
            status=SandboxStatus.CREATING,
            executor_type="firecracker",
            timestamps=SessionTimestamps(created_at=utcnow()),
        )

        # Copy-on-write clone of the base rootfs
        base_rootfs = Path(self._config.firecracker_rootfs_image)
        if not base_rootfs.exists():
            raise SandboxError(
                f"Base rootfs image not found: {base_rootfs}",
                details={"rootfs": str(base_rootfs)},
            )
        await asyncio.to_thread(shutil.copy2, str(base_rootfs), str(rootfs_path))

        # Start the Firecracker process
        fc_binary = self._config.firecracker_binary
        process = await asyncio.create_subprocess_exec(
            fc_binary,
            "--api-sock",
            str(socket_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for the socket to become available
        for _ in range(50):
            if socket_path.exists():
                break
            await asyncio.sleep(0.1)
        else:
            process.kill()
            raise SandboxError(
                "Firecracker API socket did not appear within 5s",
                details={"socket_path": str(socket_path)},
            )

        vm = _VMHandle(
            vm_id=vm_id,
            socket_path=socket_path,
            rootfs_path=rootfs_path,
            process=process,
        )

        # Configure the VM via the Firecracker API
        try:
            await self._configure_vm(vm, spec)
            await self._start_vm(vm)
        except Exception:
            process.kill()
            self._cleanup_vm_files(vm)
            raise

        session.container_id = vm_id
        session.status = SandboxStatus.READY
        session.timestamps.started_at = utcnow()
        self._sessions[session.id] = session
        self._vms[session.id] = vm

        logger.info(
            "firecracker_vm_created",
            session_id=session.id,
            vm_id=vm_id,
            task_id=spec.task_id,
        )
        return session

    async def execute_command(
        self, session_id: str, command: str, timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run *command* inside the Firecracker VM via SSH."""
        session = self._get_session(session_id)
        vm = self._get_vm(session_id)

        allowed, reason = validate_command(command)
        if not allowed:
            raise SandboxSecurityError(
                f"Command rejected: {reason}",
                details={"command": command, "reason": reason},
            )

        session.status = SandboxStatus.RUNNING
        sequence = len(session.audit_log)
        start_time = time.monotonic()

        ssh_args = self._build_ssh_args(vm, command)

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            raw_stdout, raw_stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            exit_code = proc.returncode or 0
            stdout = raw_stdout.decode("utf-8", errors="replace")
            stderr = raw_stderr.decode("utf-8", errors="replace")
        except TimeoutError as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            session.audit_log.append(
                AuditLogEntry(
                    sequence=sequence,
                    command=command,
                    exit_code=-1,
                    stdout_truncated="",
                    stderr_truncated="TIMEOUT",
                    duration_ms=duration_ms,
                )
            )
            session.status = SandboxStatus.TIMED_OUT
            raise SandboxTimeoutError(
                f"Command timed out after {timeout}s",
                details={"command": command, "timeout": timeout},
            ) from exc

        duration_ms = (time.monotonic() - start_time) * 1000
        max_chars = 50_000
        session.audit_log.append(
            AuditLogEntry(
                sequence=sequence,
                command=command,
                exit_code=exit_code,
                stdout_truncated=stdout[:max_chars],
                stderr_truncated=stderr[:max_chars],
                duration_ms=duration_ms,
            )
        )
        session.status = SandboxStatus.READY

        logger.info(
            "fc_command_run",
            session_id=session_id,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 1),
        )
        return exit_code, stdout, stderr

    async def write_files(self, session_id: str, files: dict[str, str]) -> None:
        """Write files into the VM via SSH + base64 encoding."""
        self._get_session(session_id)
        vm = self._get_vm(session_id)

        allowed, reason = validate_files(files)
        if not allowed:
            raise SandboxSecurityError(
                f"File write rejected: {reason}",
                details={"reason": reason},
            )

        for path, content in files.items():
            clean_path = path.lstrip("/")
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            # Create parent dirs and decode into the file
            write_cmd = (
                f"mkdir -p /workspace/$(dirname {clean_path}) && "
                f"echo '{encoded}' | base64 -d > /workspace/{clean_path}"
            )
            ssh_args = self._build_ssh_args(vm, write_cmd)
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    "fc_write_file_error",
                    session_id=session_id,
                    path=clean_path,
                    stderr=stderr.decode("utf-8", errors="replace")[:500],
                )

        logger.info("fc_files_written", session_id=session_id, file_count=len(files))

    async def read_files(self, session_id: str, paths: list[str]) -> dict[str, str]:
        """Read files from the VM via SSH + base64."""
        self._get_session(session_id)
        vm = self._get_vm(session_id)

        results: dict[str, str] = {}
        for path in paths:
            clean_path = path if path.startswith("/") else f"/workspace/{path}"
            read_cmd = f"base64 {clean_path} 2>/dev/null"
            ssh_args = self._build_ssh_args(vm, read_cmd)
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            raw_stdout, _ = await proc.communicate()
            if proc.returncode == 0 and raw_stdout:
                try:
                    results[path] = base64.b64decode(raw_stdout).decode("utf-8", errors="replace")
                except Exception:
                    logger.warning("fc_read_decode_error", session_id=session_id, path=path)
            else:
                logger.warning("fc_file_not_found", session_id=session_id, path=path)

        return results

    async def destroy(self, session_id: str) -> None:
        """Shut down the microVM and clean up resources."""
        session = self._get_session(session_id)
        vm = self._vms.get(session_id)

        if vm:
            # Try graceful shutdown via API first
            try:
                await self._api_call(vm, "PUT", "/actions", {"action_type": "SendCtrlAltDel"})
                if vm.process:
                    try:
                        await asyncio.wait_for(vm.process.wait(), timeout=5.0)
                    except TimeoutError:
                        vm.process.kill()
            except Exception:
                if vm.process:
                    vm.process.kill()

            self._cleanup_vm_files(vm)
            del self._vms[session_id]

        session.status = SandboxStatus.DESTROYED
        session.timestamps.destroyed_at = utcnow()
        del self._sessions[session_id]

        logger.info("firecracker_vm_destroyed", session_id=session_id)

    # ── Query ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SandboxSession | None:
        """Return the session for *session_id*, or ``None``."""
        return self._sessions.get(session_id)

    # ── Firecracker API helpers ──────────────────────────────────────

    async def _api_call(
        self, vm: _VMHandle, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an HTTP request to the Firecracker API via Unix socket."""
        transport = httpx.AsyncHTTPTransport(uds=str(vm.socket_path))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.request(
                method,
                path,
                json=body,
                timeout=10.0,
            )
            if response.status_code >= 400:
                text = response.text
                raise SandboxError(
                    f"Firecracker API error: {response.status_code} on {method} {path}",
                    details={"status": response.status_code, "body": text},
                )
            if response.content:
                return dict(response.json())
            return {}

    async def _configure_vm(self, vm: _VMHandle, spec: SandboxSpec) -> None:
        """Configure a Firecracker VM's machine config, boot source, and drives."""
        # Machine config
        await self._api_call(
            vm,
            "PUT",
            "/machine-config",
            {
                "vcpu_count": spec.resource_limits.cpu_cores,
                "mem_size_mib": spec.resource_limits.memory_mb,
            },
        )

        # Boot source
        kernel_path = self._config.firecracker_kernel_image
        await self._api_call(
            vm,
            "PUT",
            "/boot-source",
            {
                "kernel_image_path": kernel_path,
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
            },
        )

        # Root drive
        await self._api_call(
            vm,
            "PUT",
            "/drives/rootfs",
            {
                "drive_id": "rootfs",
                "path_on_host": str(vm.rootfs_path),
                "is_root_device": True,
                "is_read_only": False,
            },
        )

        # Network interface (only if egress is allowed)
        if spec.network_policy.allow_egress:
            logger.info(
                "fc_network_requested",
                vm_id=vm.vm_id,
                note="TAP device setup required for network access",
            )

    async def _start_vm(self, vm: _VMHandle) -> None:
        """Boot the Firecracker VM."""
        await self._api_call(vm, "PUT", "/actions", {"action_type": "InstanceStart"})
        logger.info("fc_vm_started", vm_id=vm.vm_id)

    def _build_ssh_args(self, vm: _VMHandle, command: str) -> list[str]:
        """Build the SSH argument list for executing inside the VM."""
        key_path = self._config.firecracker_ssh_key_path
        user = self._config.firecracker_ssh_user
        port = str(self._config.firecracker_ssh_port)
        ip = vm.ip_address or "192.168.0.2"

        return [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "ConnectTimeout=10",
            "-i",
            key_path,
            "-p",
            port,
            f"{user}@{ip}",
            command,
        ]

    def _cleanup_vm_files(self, vm: _VMHandle) -> None:
        """Remove socket and rootfs files for a destroyed VM."""
        import contextlib

        with contextlib.suppress(OSError):
            vm.socket_path.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            vm.rootfs_path.unlink(missing_ok=True)

    # ── Internal helpers ─────────────────────────────────────────────

    def _get_session(self, session_id: str) -> SandboxSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SandboxError(
                f"No active session: {session_id}",
                details={"session_id": session_id},
            )
        return session

    def _get_vm(self, session_id: str) -> _VMHandle:
        vm = self._vms.get(session_id)
        if vm is None:
            raise SandboxError(
                f"No VM handle for session: {session_id}",
                details={"session_id": session_id},
            )
        return vm
