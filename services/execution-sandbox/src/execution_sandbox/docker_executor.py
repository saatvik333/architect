"""Docker-backed sandbox executor."""

from __future__ import annotations

import asyncio
import io
import tarfile
import time
from typing import Any

import docker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    def __init__(
        self,
        docker_socket: str = "/var/run/docker.sock",
        docker_host: str = "",
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        base_url = docker_host if docker_host else f"unix://{docker_socket}"
        self._client: docker.DockerClient = docker.DockerClient(base_url=base_url)
        self._sessions: dict[str, SandboxSession] = {}
        self._session_factory = session_factory

    # ── Persistence ─────────────────────────────────────────────────

    async def _persist_session(self, session: SandboxSession) -> None:
        """Save session state to the database if a session factory is configured."""
        if self._session_factory is None:
            return
        from architect_db.models.sandbox import SandboxSession as SandboxSessionRow
        from architect_db.repositories.sandbox_repo import SandboxSessionRepository

        async with self._session_factory() as db_session:
            repo = SandboxSessionRepository(db_session)
            existing = await repo.get_by_id(session.id)
            if existing is None:
                row = SandboxSessionRow(
                    id=session.id,
                    task_id=session.spec.task_id,
                    agent_id=session.spec.agent_id,
                    status=session.status.value,
                    container_id=session.container_id or "",
                    image=session.spec.base_image,
                    created_at=session.timestamps.created_at,
                    started_at=session.timestamps.started_at,
                )
                db_session.add(row)
            else:
                existing.status = session.status.value
                existing.container_id = session.container_id or ""
                existing.started_at = session.timestamps.started_at
                existing.completed_at = session.timestamps.completed_at
                existing.destroyed_at = session.timestamps.destroyed_at
            await db_session.commit()

    async def load_active_sessions_from_db(self) -> int:
        """Load active sessions from the database on startup.

        Returns the number of sessions restored.
        """
        if self._session_factory is None:
            return 0
        from architect_db.repositories.sandbox_repo import SandboxSessionRepository

        async with self._session_factory() as db_session:
            repo = SandboxSessionRepository(db_session)
            active_rows = await repo.get_active()

        restored = 0
        for row in active_rows:
            if row.id in self._sessions:
                continue
            # Check if the container still exists in Docker
            try:
                container = await asyncio.to_thread(  # noqa: F841
                    self._client.containers.get, row.container_id
                )
            except docker.errors.NotFound:
                logger.info("db_session_container_gone", session_id=row.id)
                continue
            except docker.errors.APIError:
                logger.warning("db_session_check_failed", session_id=row.id)
                continue

            # Reconstruct in-memory session
            session = SandboxSession(
                spec=SandboxSpec(
                    task_id=row.task_id or "",
                    agent_id=row.agent_id or "",
                    base_image=row.image or "",
                ),
                status=SandboxStatus(row.status),
                timestamps=SessionTimestamps(
                    created_at=row.created_at,
                    started_at=row.started_at,
                ),
            )
            session.id = row.id
            session.container_id = row.container_id
            self._sessions[session.id] = session
            restored += 1
            logger.info("session_restored_from_db", session_id=row.id)

        if restored:
            logger.info("sessions_restored", count=restored)
        return restored

    # ── Lifecycle ────────────────────────────────────────────────────

    async def create(self, spec: SandboxSpec) -> SandboxSession:
        """Create a Docker container from *spec* and return the session."""
        config = create_container_config(spec)

        session = SandboxSession(
            spec=spec,
            status=SandboxStatus.CREATING,
            timestamps=SessionTimestamps(created_at=utcnow()),
        )

        # Add session-level label so orphans can be reconciled
        config.setdefault("labels", {})
        config["labels"]["architect.session_id"] = session.id
        config["labels"]["architect.component"] = "execution-sandbox"

        def _create() -> str:
            container = self._client.containers.run(**config)
            return str(container.id)

        try:
            container_id = await asyncio.to_thread(_create)
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
        await self._persist_session(session)

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
                asyncio.to_thread(_run),
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
            usage = await asyncio.to_thread(check_resource_usage, container)
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

        await asyncio.to_thread(_write)

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
                            # Tar slip protection: reject absolute or
                            # parent-traversal paths
                            if member.name.startswith("/") or ".." in member.name:
                                logger.warning(
                                    "tar_slip_rejected",
                                    session_id=session_id,
                                    member_name=member.name,
                                    path=path,
                                )
                                continue
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

        return await asyncio.to_thread(_read)

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

            await asyncio.to_thread(_destroy)

        session.status = SandboxStatus.DESTROYED
        session.timestamps.destroyed_at = utcnow()
        await self._persist_session(session)
        del self._sessions[session_id]

        logger.info("sandbox_destroyed", session_id=session_id)

    # ── Orphan reconciliation ─────────────────────────────────────

    async def _reconcile_orphans(self) -> int:
        """Remove containers labelled as execution-sandbox that have no
        matching in-memory session.

        Intended to be called once at startup to clean up containers left
        behind by a previous crash.

        Returns:
            The number of orphaned containers removed.
        """

        def _reconcile() -> int:
            removed = 0
            try:
                containers = self._client.containers.list(
                    all=True,
                    filters={"label": "architect.component=execution-sandbox"},
                )
            except docker.errors.APIError:
                logger.error("orphan_reconcile_list_failed")
                return 0

            known_ids = {s.container_id for s in self._sessions.values() if s.container_id}

            for container in containers:
                if container.id not in known_ids:
                    try:
                        container.remove(force=True)
                        removed += 1
                        logger.info(
                            "orphan_container_removed",
                            container_id=str(container.id)[:12],
                        )
                    except docker.errors.APIError as exc:
                        logger.warning(
                            "orphan_remove_failed",
                            container_id=str(container.id)[:12],
                            error=str(exc),
                        )
            return removed

        count = await asyncio.to_thread(_reconcile)
        if count:
            logger.info("orphan_reconciliation_complete", removed=count)
        return count

    # ── Query ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SandboxSession | None:
        """Return the session for *session_id*, or ``None``."""
        return self._sessions.get(session_id)

    def active_session_count(self) -> int:
        """Return the number of currently active sessions."""
        return len(self._sessions)

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
