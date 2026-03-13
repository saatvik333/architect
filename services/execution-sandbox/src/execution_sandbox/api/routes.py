"""HTTP route handlers for the Execution Sandbox API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from architect_common.enums import HealthStatus, SandboxStatus
from architect_common.errors import SandboxError, SandboxSecurityError, SandboxTimeoutError
from execution_sandbox.docker_executor import DockerExecutor
from execution_sandbox.models import SandboxSpec

from .dependencies import get_executor

router = APIRouter()


# ── Request / response schemas ───────────────────────────────────────


class CreateSandboxRequest(BaseModel):
    spec: SandboxSpec


class ExecCommandRequest(BaseModel):
    command: str
    timeout: int = Field(default=60, ge=1, le=3600)


class WriteFilesRequest(BaseModel):
    files: dict[str, str]


class ReadFilesRequest(BaseModel):
    paths: list[str]


class HealthResponse(BaseModel):
    status: HealthStatus
    active_sandboxes: int = 0


class SandboxResponse(BaseModel):
    """Serialisable subset of a :class:`SandboxSession`."""

    id: str
    status: SandboxStatus
    container_id: str | None = None
    audit_log_length: int = 0
    exit_code: int | None = None


class ExecResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class ReadFilesResponse(BaseModel):
    files: dict[str, str]


# ── Helper ───────────────────────────────────────────────────────────

ExecutorDep = Annotated[DockerExecutor, Depends(get_executor)]


def _to_sandbox_response(session: Any) -> SandboxResponse:
    return SandboxResponse(
        id=session.id,
        status=session.status,
        container_id=session.container_id,
        audit_log_length=len(session.audit_log),
        exit_code=session.exit_code,
    )


# ── Routes ───────────────────────────────────────────────────────────


@router.post(
    "/sandbox/create",
    response_model=SandboxResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox(
    body: CreateSandboxRequest,
    executor: ExecutorDep,
) -> SandboxResponse:
    """Provision a new isolated sandbox container."""
    try:
        session = await executor.create(body.spec)
    except SandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return _to_sandbox_response(session)


@router.post(
    "/sandbox/{session_id}/exec",
    response_model=ExecResponse,
)
async def exec_command(
    session_id: str,
    body: ExecCommandRequest,
    executor: ExecutorDep,
) -> ExecResponse:
    """Execute a shell command inside an existing sandbox."""
    try:
        exit_code, stdout, stderr = await executor.execute_command(
            session_id, body.command, body.timeout
        )
    except SandboxSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SandboxTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc)) from exc
    except SandboxError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ExecResponse(exit_code=exit_code, stdout=stdout, stderr=stderr)


@router.post(
    "/sandbox/{session_id}/files",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def write_files(
    session_id: str,
    body: WriteFilesRequest,
    executor: ExecutorDep,
) -> None:
    """Write files into a sandbox container."""
    try:
        await executor.write_files(session_id, body.files)
    except SandboxSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SandboxError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sandbox/{session_id}/files",
    response_model=ReadFilesResponse,
)
async def read_files(
    session_id: str,
    paths: list[str],
    executor: ExecutorDep,
) -> ReadFilesResponse:
    """Read files from a sandbox container."""
    try:
        files = await executor.read_files(session_id, paths)
    except SandboxError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ReadFilesResponse(files=files)


@router.delete(
    "/sandbox/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def destroy_sandbox(
    session_id: str,
    executor: ExecutorDep,
) -> None:
    """Destroy a sandbox container and free resources."""
    try:
        await executor.destroy(session_id)
    except SandboxError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sandbox/{session_id}",
    response_model=SandboxResponse,
)
async def get_session(
    session_id: str,
    executor: ExecutorDep,
) -> SandboxResponse:
    """Get current state of a sandbox session."""
    session = executor.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active session: {session_id}",
        )
    return _to_sandbox_response(session)


@router.get("/health", response_model=HealthResponse)
async def health_check(executor: ExecutorDep) -> HealthResponse:
    """Liveness / readiness probe."""
    active = len(executor._sessions)
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        active_sandboxes=active,
    )
