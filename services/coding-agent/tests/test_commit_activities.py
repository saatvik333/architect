"""Tests for commit_code and update_world_state Temporal activities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from coding_agent.temporal.activities import commit_code, update_world_state


class TestCommitCodeActivity:
    """Tests for the ``commit_code`` activity."""

    async def test_commit_code_success(self) -> None:
        """Activity delegates to GitCommitter and returns hash + count."""
        files = [
            {"path": "src/hello.py", "content": "print('hi')"},
            {"path": "tests/test_hello.py", "content": "def test(): pass", "is_test": True},
        ]

        mock_committer = AsyncMock()
        mock_committer.commit.return_value = "a" * 40

        with patch(
            "coding_agent.temporal.activities.GitCommitter",
            return_value=mock_committer,
        ):
            result = await commit_code(files, "feat: add hello", "/repo")

        assert result["commit_hash"] == "a" * 40
        assert result["files_written"] == 2
        mock_committer.commit.assert_awaited_once()

    async def test_commit_code_propagates_error(self) -> None:
        """Activity re-raises GitCommitError from the committer."""
        from coding_agent.git import GitCommitError

        mock_committer = AsyncMock()
        mock_committer.commit.side_effect = GitCommitError("not a repo")

        with (
            patch(
                "coding_agent.temporal.activities.GitCommitter",
                return_value=mock_committer,
            ),
            pytest.raises(GitCommitError, match="not a repo"),
        ):
            await commit_code([{"path": "f.py", "content": "x"}], "msg", "/bad")


class TestUpdateWorldStateActivity:
    """Tests for the ``update_world_state`` activity."""

    async def test_update_world_state_success(self) -> None:
        """Activity creates a proposal and commits it successfully."""
        commit_hash = "b" * 40

        mock_client = AsyncMock()

        # GET /api/v1/state
        state_response = MagicMock()
        state_response.json.return_value = {
            "version": 1,
            "repo": {"commit_hash": "a" * 40},
        }
        state_response.raise_for_status = MagicMock()

        # POST /api/v1/proposals
        proposal_response = MagicMock()
        proposal_response.json.return_value = {"proposal_id": "prop-mock000001"}
        proposal_response.raise_for_status = MagicMock()

        # POST /api/v1/proposals/{id}/commit
        commit_response = MagicMock()
        commit_response.json.return_value = {
            "proposal_id": "prop-mock000001",
            "accepted": True,
        }
        commit_response.raise_for_status = MagicMock()

        mock_client.get.return_value = state_response
        mock_client.post.side_effect = [proposal_response, commit_response]

        # Make the async context manager work
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("coding_agent.temporal.activities.httpx.AsyncClient", return_value=mock_client):
            result = await update_world_state(
                commit_hash=commit_hash,
                task_id="task-test000001",
                agent_id="agent-test00001",
                wsl_base_url="http://wsl:8001",
            )

        assert result["proposal_id"] == "prop-mock000001"
        assert result["accepted"] is True

    async def test_update_world_state_connection_error(self) -> None:
        """Activity returns empty result when WSL is not reachable."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("coding_agent.temporal.activities.httpx.AsyncClient", return_value=mock_client):
            result = await update_world_state(
                commit_hash="c" * 40,
                task_id="task-test000001",
                agent_id="agent-test00001",
                wsl_base_url="http://wsl:8001",
            )

        assert result["proposal_id"] == ""
        assert result["accepted"] is False

    async def test_update_world_state_no_repo_in_state(self) -> None:
        """Activity handles missing repo field in world state gracefully."""
        mock_client = AsyncMock()

        state_response = MagicMock()
        state_response.json.return_value = {"version": 0}
        state_response.raise_for_status = MagicMock()

        proposal_response = MagicMock()
        proposal_response.json.return_value = {"proposal_id": "prop-new000001"}
        proposal_response.raise_for_status = MagicMock()

        commit_response = MagicMock()
        commit_response.json.return_value = {
            "proposal_id": "prop-new000001",
            "accepted": True,
        }
        commit_response.raise_for_status = MagicMock()

        mock_client.get.return_value = state_response
        mock_client.post.side_effect = [proposal_response, commit_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("coding_agent.temporal.activities.httpx.AsyncClient", return_value=mock_client):
            result = await update_world_state(
                commit_hash="d" * 40,
                task_id="task-test000001",
                agent_id="agent-test00001",
                wsl_base_url="http://wsl:8001",
            )

        assert result["proposal_id"] == "prop-new000001"
        assert result["accepted"] is True
