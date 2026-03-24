"""Tests for Coding Agent Temporal activities."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from architect_common.enums import SandboxStatus
from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse
from architect_sandbox_client.client import SandboxClient
from architect_sandbox_client.models import CommandResult, ExecutionResult
from coding_agent.config import CodingAgentConfig
from coding_agent.temporal.activities import CodingAgentActivities

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_activities(
    *,
    llm_client: LLMClient | None = None,
    sandbox_client: SandboxClient | None = None,
    config: CodingAgentConfig | None = None,
) -> CodingAgentActivities:
    """Construct a CodingAgentActivities with mock defaults."""
    return CodingAgentActivities(
        llm_client=llm_client or AsyncMock(spec=LLMClient),
        sandbox_client=sandbox_client or AsyncMock(spec=SandboxClient),
        config=config or CodingAgentConfig(),
    )


def _make_run_data(**overrides: Any) -> dict[str, Any]:
    """Build a minimal run_data dict for activity inputs."""
    data: dict[str, Any] = {
        "task_id": "task-test000001",
        "agent_id": "agent-test000001",
        "spec_context": {
            "spec_hash": "a" * 64,
            "title": "Test Feature",
            "description": "Implement a test feature.",
            "acceptance_criteria": ["Tests pass"],
            "constraints": [],
        },
        "codebase_context": {
            "commit_hash": "b" * 40,
            "relevant_files": [],
            "file_contents": {},
            "total_tokens_estimate": 100,
        },
        "config": {},
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# plan_task
# ---------------------------------------------------------------------------


class TestPlanTask:
    """Tests for the plan_task activity."""

    @patch("coding_agent.temporal.activities.activity")
    async def test_returns_plan_string(self, mock_activity: MagicMock) -> None:
        """plan_task should return a markdown plan string from the LLM."""
        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = LLMResponse(
            content="## Plan\n1. Create module\n2. Write tests",
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(llm_client=mock_llm)
        run_data = _make_run_data()

        result = await activities.plan_task(run_data)

        assert isinstance(result, str)
        assert "Plan" in result
        mock_llm.generate.assert_awaited_once()

    @patch("coding_agent.temporal.activities.activity")
    async def test_passes_spec_and_codebase_to_planner(self, mock_activity: MagicMock) -> None:
        """plan_task should validate spec and codebase contexts from run_data."""
        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = LLMResponse(
            content="plan output",
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(llm_client=mock_llm)
        run_data = _make_run_data()

        await activities.plan_task(run_data)

        # Verify the LLM was called (planner uses it)
        assert mock_llm.generate.await_count == 1

    @patch("coding_agent.temporal.activities.activity")
    async def test_handles_empty_spec_context(self, mock_activity: MagicMock) -> None:
        """plan_task should handle empty/default spec context gracefully."""
        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = LLMResponse(
            content="minimal plan",
            model_id="claude-sonnet-4-20250514",
            input_tokens=50,
            output_tokens=20,
            stop_reason="end_turn",
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(llm_client=mock_llm)
        run_data = _make_run_data(spec_context={}, codebase_context={})

        result = await activities.plan_task(run_data)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_code
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Tests for the generate_code activity."""

    @patch("coding_agent.temporal.activities.activity")
    async def test_returns_serialised_file_list(self, mock_activity: MagicMock) -> None:
        """generate_code should return a list of file dicts."""
        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = LLMResponse(
            content=(
                "```python\n"
                "# src/feature.py\n"
                "def hello() -> str:\n"
                '    return "hello"\n'
                "```\n"
                "\n"
                "```python\n"
                "# tests/test_feature.py\n"
                "from src.feature import hello\n"
                "\n"
                "def test_hello() -> None:\n"
                '    assert hello() == "hello"\n'
                "```"
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=200,
            output_tokens=100,
            stop_reason="end_turn",
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(llm_client=mock_llm)
        plan = "## Plan\n1. Create feature.py\n2. Write tests"
        run_data = _make_run_data()

        result = await activities.generate_code(plan, run_data)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all("path" in f and "content" in f for f in result)

    @patch("coding_agent.temporal.activities.activity")
    async def test_file_dicts_are_json_serialisable(self, mock_activity: MagicMock) -> None:
        """Returned file dicts should be JSON-serialisable (mode='json')."""
        import json

        mock_llm = AsyncMock(spec=LLMClient)
        mock_llm.generate.return_value = LLMResponse(
            content=("```python\n# src/mod.py\nx = 1\n```"),
            model_id="claude-sonnet-4-20250514",
            input_tokens=50,
            output_tokens=20,
            stop_reason="end_turn",
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(llm_client=mock_llm)
        result = await activities.generate_code("plan", _make_run_data())

        # Should not raise
        json.dumps(result)


# ---------------------------------------------------------------------------
# execute_in_sandbox
# ---------------------------------------------------------------------------


class TestExecuteInSandbox:
    """Tests for the execute_in_sandbox activity."""

    @patch("coding_agent.temporal.activities.activity")
    async def test_executes_commands_in_sandbox(self, mock_activity: MagicMock) -> None:
        """Activity should call sandbox_client.execute with correct request."""
        mock_sandbox = AsyncMock(spec=SandboxClient)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-test000001",
            status=SandboxStatus.COMPLETED,
            command_results=[
                CommandResult(
                    command="pytest",
                    exit_code=0,
                    stdout="1 passed",
                    stderr="",
                    duration_ms=200,
                ),
            ],
            total_duration_ms=200,
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(sandbox_client=mock_sandbox)
        files = [{"path": "src/main.py", "content": "print('hi')"}]
        commands = ["pytest"]

        result = await activities.execute_in_sandbox(files, commands)

        assert result["session_id"] == "sbx-test000001"
        assert result["status"] == SandboxStatus.COMPLETED.value
        mock_sandbox.execute.assert_awaited_once()

    @patch("coding_agent.temporal.activities.activity")
    async def test_uses_run_data_for_ids(self, mock_activity: MagicMock) -> None:
        """When run_data is provided, its task_id and agent_id are used."""
        mock_sandbox = AsyncMock(spec=SandboxClient)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-x",
            status=SandboxStatus.COMPLETED,
            command_results=[],
            total_duration_ms=0,
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(sandbox_client=mock_sandbox)
        run_data = {"task_id": "task-custom001", "agent_id": "agent-custom01"}

        await activities.execute_in_sandbox([], ["echo hi"], run_data)

        # Verify the request was built with the custom IDs
        call_args = mock_sandbox.execute.call_args
        request = call_args[0][0]
        assert request.task_id == "task-custom001"
        assert request.agent_id == "agent-custom01"

    @patch("coding_agent.temporal.activities.activity")
    async def test_default_ids_when_no_run_data(self, mock_activity: MagicMock) -> None:
        """When run_data is None, default placeholder IDs are used."""
        mock_sandbox = AsyncMock(spec=SandboxClient)
        mock_sandbox.execute.return_value = ExecutionResult(
            session_id="sbx-y",
            status=SandboxStatus.COMPLETED,
            command_results=[],
            total_duration_ms=0,
        )
        mock_activity.logger = MagicMock()

        activities = _make_activities(sandbox_client=mock_sandbox)
        await activities.execute_in_sandbox([], ["echo"], None)

        call_args = mock_sandbox.execute.call_args
        request = call_args[0][0]
        assert request.task_id == "task-temporal00000"
        assert request.agent_id == "agent-temporal0000"


# ---------------------------------------------------------------------------
# commit_code
# ---------------------------------------------------------------------------


class TestCommitCode:
    """Tests for the commit_code activity."""

    @patch("coding_agent.temporal.activities.activity")
    @patch("coding_agent.temporal.activities.GitCommitter")
    async def test_returns_commit_hash_and_count(
        self, mock_git_committer: MagicMock, mock_activity: MagicMock
    ) -> None:
        """commit_code should return commit_hash and files_written."""
        mock_committer = AsyncMock()
        mock_committer.commit.return_value = "a" * 40
        mock_git_committer.return_value = mock_committer
        mock_activity.logger = MagicMock()

        activities = _make_activities()
        files = [
            {"path": "src/main.py", "content": "print('hi')", "is_test": False},
            {"path": "tests/test_main.py", "content": "def test(): pass", "is_test": True},
        ]

        result = await activities.commit_code(files, "feat: add feature", "/workspace/repo")  # nosec B108

        assert result["commit_hash"] == "a" * 40
        assert result["files_written"] == 2
        mock_committer.commit.assert_awaited_once()

    @patch("coding_agent.temporal.activities.activity")
    @patch("coding_agent.temporal.activities.GitCommitter")
    async def test_propagates_git_commit_error(
        self, mock_git_committer: MagicMock, mock_activity: MagicMock
    ) -> None:
        """commit_code should re-raise GitCommitError."""
        from coding_agent.git import GitCommitError

        mock_committer = AsyncMock()
        mock_committer.commit.side_effect = GitCommitError("not a git repo")
        mock_git_committer.return_value = mock_committer
        mock_activity.logger = MagicMock()

        activities = _make_activities()
        files = [{"path": "f.py", "content": "x = 1", "is_test": False}]

        with pytest.raises(GitCommitError, match="not a git repo"):
            await activities.commit_code(files, "msg", "/nonexistent")


# ---------------------------------------------------------------------------
# update_world_state
# ---------------------------------------------------------------------------


class TestUpdateWorldState:
    """Tests for the update_world_state activity."""

    @patch("coding_agent.temporal.activities.activity")
    async def test_successful_update(self, mock_activity: MagicMock) -> None:
        """update_world_state should POST a proposal and commit it."""
        mock_activity.logger = MagicMock()

        activities = _make_activities()

        with patch("coding_agent.temporal.activities.httpx.AsyncClient") as mock_http_client:
            mock_client = AsyncMock()

            # GET /api/v1/state
            state_resp = MagicMock()
            state_resp.json.return_value = {"repo": {"commit_hash": "old" * 13 + "o"}}
            state_resp.raise_for_status = MagicMock()

            # POST /api/v1/proposals
            proposal_resp = MagicMock()
            proposal_resp.json.return_value = {"proposal_id": "prop-abc123"}
            proposal_resp.raise_for_status = MagicMock()

            # POST /api/v1/proposals/{id}/commit
            commit_resp = MagicMock()
            commit_resp.json.return_value = {"accepted": True}
            commit_resp.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=state_resp)
            mock_client.post = AsyncMock(side_effect=[proposal_resp, commit_resp])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_http_client.return_value = mock_client

            result = await activities.update_world_state(
                "c" * 40, "task-t1", "agent-a1", "http://localhost:8001"
            )

        assert result["proposal_id"] == "prop-abc123"
        assert result["accepted"] is True

    @patch("coding_agent.temporal.activities.activity")
    async def test_handles_http_error_gracefully(self, mock_activity: MagicMock) -> None:
        """update_world_state should return empty/False on HTTP errors."""
        mock_activity.logger = MagicMock()

        activities = _make_activities()

        with patch("coding_agent.temporal.activities.httpx.AsyncClient") as mock_http_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_http_client.return_value = mock_client

            result = await activities.update_world_state(
                "d" * 40, "task-t2", "agent-a2", "http://localhost:9999"
            )

        assert result["proposal_id"] == ""
        assert result["accepted"] is False

    @patch("coding_agent.temporal.activities.activity")
    async def test_handles_no_repo_in_state(self, mock_activity: MagicMock) -> None:
        """When state has no repo key, old_commit should be None."""
        mock_activity.logger = MagicMock()

        activities = _make_activities()

        with patch("coding_agent.temporal.activities.httpx.AsyncClient") as mock_http_client:
            mock_client = AsyncMock()

            state_resp = MagicMock()
            state_resp.json.return_value = {}  # no "repo" key
            state_resp.raise_for_status = MagicMock()

            proposal_resp = MagicMock()
            proposal_resp.json.return_value = {"proposal_id": "prop-norepo"}
            proposal_resp.raise_for_status = MagicMock()

            commit_resp = MagicMock()
            commit_resp.json.return_value = {"accepted": True}
            commit_resp.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=state_resp)
            mock_client.post = AsyncMock(side_effect=[proposal_resp, commit_resp])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_http_client.return_value = mock_client

            result = await activities.update_world_state(
                "e" * 40, "task-t3", "agent-a3", "http://localhost:8001"
            )

        assert result["accepted"] is True

        # Verify the proposal had old_value = None
        post_calls = mock_client.post.call_args_list
        proposal_payload = post_calls[0][1]["json"]
        assert proposal_payload["mutations"][0]["old_value"] is None
