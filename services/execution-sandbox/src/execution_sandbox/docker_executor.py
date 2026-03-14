"""Docker-backed sandbox executor."""

from __future__ import annotations

import asyncio
import io
import tarfile
import time
from typing import Any

import docker

from architect_common.enums import SandboxStatus
from architect_common.errors import (
    SandboxError,
    SandboxResourceError,
    SandboxSecurityError,
    SandboxTimeoutError,
)
from architect_common.logging import get_logger
from architect_common.types import utcnow
from execution_sandbox.executor_base import ExecutorBase
from execution_sandbox.models import (
    AuditLogEntry,
    ResourceUsage,
    SandboxSession,
    SandboxSpec,
    SessionTimestamps,
)
from execution_sandbox.resource_limits import check_resource_usage, create_container_config
from execution_sandbox.security import _resolve_sandbox_path, validate_command, validate_files

logger = get_logger(component="docker_executor")


class DockerExecutor(ExecutorBase):
    """Runs sandboxed code inside Docker containers.

    Each :class:`SandboxSession` maps to exactly one Docker container.
    """

    def __init__(self, docker_socket: str = "/var/run/docker.sock") -> None:
        self._client: docker.DockerClient = docker.DockerClient(base_url=f"unix://{docker_socket}")
        self._sessions: dict[str, SandboxSession] = {}

    # ── Lifecycle ────────────────────────────────────────────────────

    async def create(self, spec: SandboxSpec) -> SandboxSession:
        """Create a Docker container from *spec* and return the session."""
        config = create_container_config(spec)

        session = SandboxSession(
            spec=spec,
            status=SandboxStatus.CREATING,
            timestamps=SessionTimestamps(created_at=utcnow()),
        )

        def _create() -> str:
            container = self._client.containers.run(**config)
            return str(container.id)

        try:
            container_id = await asyncio.get_event_loop().run_in_executor(None, _create)
        except docker.errors.ImageNotFound as exc:
            session.status = SandboxStatus.ERROR
            raise SandboxError(
                f"Base image not found: {spec.base_image}",
                details={"image": spec.base_image},
            ) from exc
        except docker.errors.APIError as exc:
            session.status = SandboxStatus.ERROR
            raise SandboxError(
                f"Docker API error during container creation: {exc}",
                details={"error": str(exc)},
            ) from exc

        session.container_id = container_id
        session.status = SandboxStatus.READY
        session.timestamps.started_at = utcnow()
        self._sessions[session.id] = session

        logger.info(
            "sandbox_created",
            session_id=session.id,
            container_id=container_id[:12],
            task_id=spec.task_id,
        )
        return session

    async def run_command(
        self, session_id: str, command: str, timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run *command* inside the sandbox container.

        This is the implementation of
        :meth:`ExecutorBase.execute_command`.

        Returns:
            ``(exit_code, stdout, stderr)`` tuple.
        """
        session = self._get_session(session_id)

        # Security check
        allowed, reason = validate_command(command)
        if not allowed:
            raise SandboxSecurityError(
                f"Command rejected: {reason}",
                details={"command": command, "reason": reason},
            )

        container = self._get_container(session)
        session.status = SandboxStatus.RUNNING

        sequence = len(session.audit_log)
        start_time = time.monotonic()

        def _run() -> tuple[int, str, str]:
            result = container.exec_run(
                cmd=["sh", "-c", command],
                stdout=True,
                stderr=True,
                demux=True,
                workdir="/workspace",
                user="1000:1000",
            )
            exit_code: int = result.exit_code
            raw_stdout, raw_stderr = result.output
            stdout = (raw_stdout or b"").decode("utf-8", errors="replace")
            stderr = (raw_stderr or b"").decode("utf-8", errors="replace")
            return exit_code, stdout, stderr

        try:
            exit_code, stdout, stderr = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _run),
                timeout=timeout,
            )
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

        # Truncate output for audit log
        max_chars = 50_000
        audit_entry = AuditLogEntry(
            sequence=sequence,
            command=command,
            exit_code=exit_code,
            stdout_truncated=stdout[:max_chars],
            stderr_truncated=stderr[:max_chars],
            duration_ms=duration_ms,
        )
        session.audit_log.append(audit_entry)

        # Update resource usage
        try:
            usage = await asyncio.get_event_loop().run_in_executor(
                None, check_resource_usage, container
            )
            session.resource_usage = ResourceUsage(**usage)
        except Exception:
            logger.debug("resource_stats_unavailable", session_id=session_id)

        session.status = SandboxStatus.READY

        logger.info(
            "command_run",
            session_id=session_id,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 1),
        )
        return exit_code, stdout, stderr

    # Satisfy the abstract interface
    async def execute_command(
        self, session_id: str, command: str, timeout: int = 60
    ) -> tuple[int, str, str]:
        """Delegate to :meth:`run_command`."""
        return await self.run_command(session_id, command, timeout)

    async def write_files(self, session_id: str, files: dict[str, str]) -> None:
        """Write files into the sandbox via ``put_archive``."""
        session = self._get_session(session_id)

        # Security check
        allowed, reason = validate_files(files)
        if not allowed:
            raise SandboxSecurityError(
                f"File write rejected: {reason}",
                details={"reason": reason},
            )

        container = self._get_container(session)

        def _write() -> None:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for path, content in files.items():
                    clean_path = path.lstrip("/")
                    data = content.encode("utf-8")
                    info = tarfile.TarInfo(name=clean_path)
                    info.size = len(data)
                    info.uid = 1000
                    info.gid = 1000
                    info.mode = 0o644
                    tar.addfile(info, io.BytesIO(data))
            buf.seek(0)
            container.put_archive("/workspace", buf)

        await asyncio.get_event_loop().run_in_executor(None, _write)

        logger.info(
            "files_written",
            session_id=session_id,
            file_count=len(files),
        )

    async def read_files(self, session_id: str, paths: list[str]) -> dict[str, str]:
        """Read files from the sandbox via ``get_archive``."""
        session = self._get_session(session_id)

        # Validate every requested path before touching the container
        for path in paths:
            safe, reason, _resolved = _resolve_sandbox_path(path)
            if not safe:
                raise SandboxSecurityError(
                    f"File read rejected: {reason}",
                    details={"path": path, "reason": reason},
                )

        container = self._get_container(session)

        def _read() -> dict[str, str]:
            results: dict[str, str] = {}
            for path in paths:
                clean_path = path if path.startswith("/") else f"/workspace/{path}"
                try:
                    archive_stream, _stat = container.get_archive(clean_path)
                    buf = io.BytesIO()
                    for chunk in archive_stream:
                        buf.write(chunk)
                    buf.seek(0)
                    with tarfile.open(fileobj=buf, mode="r") as tar:
                        for member in tar.getmembers():
                            if member.isfile():
                                extracted = tar.extractfile(member)
                                if extracted is not None:
                                    results[path] = extracted.read().decode(
                                        "utf-8", errors="replace"
                                    )
                except docker.errors.NotFound:
                    logger.warning("file_not_found", session_id=session_id, path=path)
                except Exception as e:
                    logger.warning(
                        "file_read_error",
                        session_id=session_id,
                        path=path,
                        error=str(e),
                    )
            return results

        return await asyncio.get_event_loop().run_in_executor(None, _read)

    async def destroy(self, session_id: str) -> None:
        """Force-remove the container and clean up session state."""
        session = self._get_session(session_id)

        if session.container_id:

            def _destroy() -> None:
                try:
                    container = self._client.containers.get(session.container_id)
                    container.remove(force=True)
                except docker.errors.NotFound:
                    logger.debug("container_already_gone", session_id=session_id)
                except docker.errors.APIError as e:
                    logger.error(
                        "container_destroy_error",
                        session_id=session_id,
                        error=str(e),
                    )

            await asyncio.get_event_loop().run_in_executor(None, _destroy)

        session.status = SandboxStatus.DESTROYED
        session.timestamps.destroyed_at = utcnow()
        del self._sessions[session_id]

        logger.info("sandbox_destroyed", session_id=session_id)

    # ── Query ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SandboxSession | None:
        """Return the session for *session_id*, or ``None``."""
        return self._sessions.get(session_id)

    # ── Internal helpers ─────────────────────────────────────────────

    def _get_session(self, session_id: str) -> SandboxSession:
        """Retrieve a session or raise :class:`SandboxError`."""
        session = self._sessions.get(session_id)
        if session is None:
            raise SandboxError(
                f"No active session: {session_id}",
                details={"session_id": session_id},
            )
        return session

    def _get_container(self, session: SandboxSession) -> Any:
        """Retrieve the Docker container for *session* or raise."""
        if not session.container_id:
            raise SandboxError(
                "Session has no container",
                details={"session_id": session.id},
            )
        try:
            return self._client.containers.get(session.container_id)
        except docker.errors.NotFound as exc:
            session.status = SandboxStatus.ERROR
            raise SandboxResourceError(
                f"Container disappeared: {session.container_id}",
                details={"container_id": session.container_id},
            ) from exc
