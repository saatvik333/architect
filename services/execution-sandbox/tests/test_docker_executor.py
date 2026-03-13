"""Tests for DockerExecutor with a mocked Docker client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from architect_common.enums import SandboxStatus
from architect_common.errors import SandboxError, SandboxSecurityError
from execution_sandbox.docker_executor import DockerExecutor
from execution_sandbox.models import SandboxSpec

# ═══════════════════════════════════════════════════════════════════════
# Fixture helpers
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def _patched_executor(
    executor: DockerExecutor,
    mock_docker_client: MagicMock,
) -> DockerExecutor:
    """Executor with mock client already injected (via conftest)."""
    # Ensure the executor's internal client is the mock
    executor._client = mock_docker_client
    return executor


# ═══════════════════════════════════════════════════════════════════════
# Container creation
# ═══════════════════════════════════════════════════════════════════════


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_returns_session(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)

        assert session.id.startswith("sbx-")
        assert session.status == SandboxStatus.READY
        assert session.container_id == "abc123def456"
        assert session.spec == sample_spec

    @pytest.mark.asyncio
    async def test_create_stores_session(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        retrieved = _patched_executor.get_session(session.id)
        assert retrieved is session

    @pytest.mark.asyncio
    async def test_create_image_not_found(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        import docker.errors

        _patched_executor._client.containers.run.side_effect = docker.errors.ImageNotFound(
            "not found"
        )

        with pytest.raises(SandboxError, match="Base image not found"):
            await _patched_executor.create(sample_spec)


# ═══════════════════════════════════════════════════════════════════════
# Command execution
# ═══════════════════════════════════════════════════════════════════════


class TestExecuteCommand:
    @pytest.mark.asyncio
    async def test_successful_command(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        exit_code, stdout, stderr = await _patched_executor.execute_command(
            session.id, "echo hello", timeout=10
        )

        assert exit_code == 0
        assert stdout == "hello world\n"
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_command_appends_audit_log(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        await _patched_executor.execute_command(session.id, "echo test", timeout=10)

        assert len(session.audit_log) == 1
        entry = session.audit_log[0]
        assert entry.sequence == 0
        assert entry.command == "echo test"
        assert entry.exit_code == 0
        assert entry.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_dangerous_command_rejected(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)

        with pytest.raises(SandboxSecurityError, match="Command rejected"):
            await _patched_executor.execute_command(session.id, "mkfs.ext4 /dev/sda1")

    @pytest.mark.asyncio
    async def test_nonexistent_session_raises(self, _patched_executor: DockerExecutor) -> None:
        with pytest.raises(SandboxError, match="No active session"):
            await _patched_executor.execute_command("nonexistent", "echo hi")


# ═══════════════════════════════════════════════════════════════════════
# File operations
# ═══════════════════════════════════════════════════════════════════════


class TestWriteFiles:
    @pytest.mark.asyncio
    async def test_write_files_calls_put_archive(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        container = _patched_executor._client.containers.get(session.container_id)

        await _patched_executor.write_files(session.id, {"main.py": "print('hello')"})

        container.put_archive.assert_called_once()
        call_args = container.put_archive.call_args
        assert call_args[0][0] == "/workspace"

    @pytest.mark.asyncio
    async def test_write_files_security_check(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)

        with pytest.raises(SandboxSecurityError, match="File write rejected"):
            await _patched_executor.write_files(session.id, {"/etc/shadow": "root::0:0:::"})


class TestReadFiles:
    @pytest.mark.asyncio
    async def test_read_files_returns_dict(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)

        # Build a tar archive for the mock to return
        import io
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = b"print('hello')"
            info = tarfile.TarInfo(name="main.py")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)

        container = _patched_executor._client.containers.get(session.container_id)
        container.get_archive.return_value = (iter([buf.getvalue()]), {"size": 100})

        result = await _patched_executor.read_files(session.id, ["main.py"])

        assert "main.py" in result
        assert result["main.py"] == "print('hello')"


# ═══════════════════════════════════════════════════════════════════════
# Destroy
# ═══════════════════════════════════════════════════════════════════════


class TestDestroy:
    @pytest.mark.asyncio
    async def test_destroy_removes_container(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        container = _patched_executor._client.containers.get(session.container_id)

        await _patched_executor.destroy(session.id)

        container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_destroy_removes_session(
        self, _patched_executor: DockerExecutor, sample_spec: SandboxSpec
    ) -> None:
        session = await _patched_executor.create(sample_spec)
        session_id = session.id

        await _patched_executor.destroy(session_id)

        assert _patched_executor.get_session(session_id) is None

    @pytest.mark.asyncio
    async def test_destroy_nonexistent_raises(self, _patched_executor: DockerExecutor) -> None:
        with pytest.raises(SandboxError, match="No active session"):
            await _patched_executor.destroy("nonexistent")
