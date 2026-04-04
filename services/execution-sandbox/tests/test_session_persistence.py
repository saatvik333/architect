"""Tests for sandbox session persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution_sandbox.docker_executor import DockerExecutor


class TestSessionPersistence:
    def test_executor_accepts_session_factory(self) -> None:
        """DockerExecutor constructor accepts optional session_factory."""
        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=None)
            assert executor._session_factory is None

    def test_executor_with_session_factory(self) -> None:
        """DockerExecutor stores session_factory when provided."""
        mock_factory = MagicMock()
        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=mock_factory)
            assert executor._session_factory is mock_factory

    @pytest.mark.asyncio
    async def test_persist_session_skips_when_no_factory(self) -> None:
        """_persist_session is a no-op when session_factory is None."""
        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=None)

        mock_session = MagicMock()
        # Should complete without error
        await executor._persist_session(mock_session)

    @pytest.mark.asyncio
    async def test_load_active_sessions_returns_zero_without_factory(self) -> None:
        """load_active_sessions_from_db returns 0 when no factory configured."""
        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=None)

        result = await executor.load_active_sessions_from_db()
        assert result == 0

    @pytest.mark.asyncio
    async def test_persist_session_creates_new_row(self) -> None:
        """_persist_session inserts a new row when session doesn't exist in DB."""
        mock_db_session = AsyncMock()
        mock_db_session.add = MagicMock()  # session.add() is synchronous in SQLAlchemy
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        # async_sessionmaker() returns an AsyncSession used as async context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=mock_factory)

        mock_session = MagicMock()
        mock_session.id = "sbx-test123"
        mock_session.spec.task_id = "task-abc"
        mock_session.spec.agent_id = "agent-xyz"
        mock_session.spec.base_image = "python:3.12"
        mock_session.status.value = "ready"
        mock_session.container_id = "container123"
        mock_session.timestamps.created_at = None
        mock_session.timestamps.started_at = None

        with (
            patch(
                "architect_db.repositories.sandbox_repo.SandboxSessionRepository",
                return_value=mock_repo,
            ),
            patch("architect_db.models.sandbox.SandboxSession"),
        ):
            await executor._persist_session(mock_session)

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_session_updates_existing_row(self) -> None:
        """_persist_session updates an existing row when session exists in DB."""
        existing_row = MagicMock()
        mock_db_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing_row)

        # async_sessionmaker() returns an AsyncSession used as async context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        with patch("execution_sandbox.docker_executor.docker.DockerClient"):
            executor = DockerExecutor(session_factory=mock_factory)

        mock_session = MagicMock()
        mock_session.id = "sbx-test123"
        mock_session.status.value = "destroyed"
        mock_session.container_id = "container123"
        mock_session.timestamps.started_at = None
        mock_session.timestamps.completed_at = None
        mock_session.timestamps.destroyed_at = None

        with patch(
            "architect_db.repositories.sandbox_repo.SandboxSessionRepository",
            return_value=mock_repo,
        ):
            await executor._persist_session(mock_session)

        assert existing_row.status == "destroyed"
        assert existing_row.container_id == "container123"
        mock_db_session.commit.assert_awaited_once()
        # Should NOT call add — it's an update
        mock_db_session.add.assert_not_called()
