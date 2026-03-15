"""End-to-end tests for the CodingAgentWorkflow using Temporal's test environment.

These tests use temporalio.testing.WorkflowEnvironment to spin up an in-memory
Temporal server and mock activities, so no external infrastructure is needed.
"""

from __future__ import annotations

from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from coding_agent.temporal.workflows import CodingAgentWorkflow

# ---------------------------------------------------------------------------
# Mock activity implementations
# ---------------------------------------------------------------------------

MOCK_PLAN = "## Plan\n1. Create module\n2. Add function\n3. Write tests"

MOCK_FILES = [
    {
        "path": "src/calculator.py",
        "content": "def add(a, b):\n    return a + b\n",
        "is_test": False,
    },
    {
        "path": "tests/test_calculator.py",
        "content": "def test_add():\n    assert add(1, 2) == 3\n",
        "is_test": True,
    },
]

MOCK_COMMIT_HASH = "abc123def456789012345678901234567890abcd"


@activity.defn(name="plan_task")
async def mock_plan_task(run_data: dict[str, Any]) -> str:
    """Return a canned implementation plan."""
    return MOCK_PLAN


@activity.defn(name="generate_code")
async def mock_generate_code(plan: str, run_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return canned generated files."""
    return MOCK_FILES


@activity.defn(name="execute_in_sandbox")
async def mock_execute_in_sandbox(
    files: list[dict[str, Any]], commands: list[str]
) -> dict[str, Any]:
    """Return a successful sandbox execution result."""
    return {
        "command_results": [
            {"command": cmd, "exit_code": 0, "stdout": "ok", "stderr": ""} for cmd in commands
        ],
    }


@activity.defn(name="commit_code")
async def mock_commit_code(
    files: list[dict[str, Any]],
    commit_message: str,
    repo_path: str,
) -> dict[str, Any]:
    """Return a canned commit result."""
    return {"commit_hash": MOCK_COMMIT_HASH, "files_written": len(files)}


@activity.defn(name="update_world_state")
async def mock_update_world_state(
    commit_hash: str,
    task_id: str,
    agent_id: str,
    wsl_base_url: str,
) -> dict[str, Any]:
    """Return a canned world-state update result."""
    return {"proposal_id": "prop-test00000000", "accepted": True}


# ---------------------------------------------------------------------------
# Failing mock activities for the failure path
# ---------------------------------------------------------------------------


@activity.defn(name="execute_in_sandbox")
async def mock_execute_in_sandbox_fail(
    files: list[dict[str, Any]], commands: list[str]
) -> dict[str, Any]:
    """Return a failed sandbox execution result."""
    return {
        "command_results": [
            {"command": commands[0], "exit_code": 1, "stdout": "", "stderr": "SyntaxError"},
        ],
    }


# Track whether commit_code was called in the failure test
_commit_called = False


@activity.defn(name="commit_code")
async def mock_commit_code_tracking(
    files: list[dict[str, Any]],
    commit_message: str,
    repo_path: str,
) -> dict[str, Any]:
    """Track that commit_code was called (should NOT happen on failure)."""
    global _commit_called
    _commit_called = True
    return {"commit_hash": MOCK_COMMIT_HASH, "files_written": len(files)}


_wsl_called = False


@activity.defn(name="update_world_state")
async def mock_update_world_state_tracking(
    commit_hash: str,
    task_id: str,
    agent_id: str,
    wsl_base_url: str,
) -> dict[str, Any]:
    """Track that update_world_state was called (should NOT happen on failure)."""
    global _wsl_called
    _wsl_called = True
    return {"proposal_id": "prop-test00000000", "accepted": True}


# ---------------------------------------------------------------------------
# Helper to build a valid run_data dict
# ---------------------------------------------------------------------------


def _make_run_data(**overrides: Any) -> dict[str, Any]:
    """Build a minimal run_data dict for the workflow."""
    data: dict[str, Any] = {
        "task_id": "task-test0000000000",
        "agent_id": "agent-test000000000",
        "max_retries": 1,
        "repo_path": "/tmp/fake-repo",
        "commit_message": "feat: test commit",
        "wsl_base_url": "http://localhost:8001",
        "spec_context": {
            "title": "Add calculator",
            "description": "Create a basic calculator module",
        },
        "codebase_context": {
            "commit_hash": "0" * 40,
            "relevant_files": [],
        },
        "config": {},
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCodingWorkflowE2E:
    """Tests for the full CodingAgentWorkflow using in-memory Temporal."""

    async def test_full_coding_workflow(self) -> None:
        """Happy path: plan -> generate -> test -> commit -> update WSL."""
        async with (
            await WorkflowEnvironment.start_local() as env,
            Worker(
                env.client,
                task_queue="test-coding-agent",
                workflows=[CodingAgentWorkflow],
                activities=[
                    mock_plan_task,
                    mock_generate_code,
                    mock_execute_in_sandbox,
                    mock_commit_code,
                    mock_update_world_state,
                ],
            ),
        ):
            run_data = _make_run_data()
            result = await env.client.execute_workflow(
                CodingAgentWorkflow.run,
                run_data,
                id="test-full-coding-workflow",
                task_queue="test-coding-agent",
            )

            # Verify the full pipeline produced expected results
            assert result["plan"] == MOCK_PLAN
            assert len(result["files"]) == 2
            assert result["commit_hash"] == MOCK_COMMIT_HASH
            assert result["wsl_accepted"] is True
            assert result["wsl_proposal_id"] == "prop-test00000000"

            # Verify test_result indicates all passed
            command_results = result["test_result"]["command_results"]
            assert all(cr["exit_code"] == 0 for cr in command_results)

    async def test_coding_workflow_fails_gracefully(self) -> None:
        """When sandbox tests fail, workflow should NOT commit or update WSL."""
        global _commit_called, _wsl_called
        _commit_called = False
        _wsl_called = False

        async with (
            await WorkflowEnvironment.start_local() as env,
            Worker(
                env.client,
                task_queue="test-coding-agent-fail",
                workflows=[CodingAgentWorkflow],
                activities=[
                    mock_plan_task,
                    mock_generate_code,
                    mock_execute_in_sandbox_fail,
                    mock_commit_code_tracking,
                    mock_update_world_state_tracking,
                ],
            ),
        ):
            run_data = _make_run_data(max_retries=1)
            result = await env.client.execute_workflow(
                CodingAgentWorkflow.run,
                run_data,
                id="test-coding-workflow-fail",
                task_queue="test-coding-agent-fail",
            )

            # Workflow completes but without committing
            assert result["commit_hash"] == ""
            assert result["wsl_accepted"] is False
            assert result["wsl_proposal_id"] == ""

            # Verify commit_code and update_world_state were never called
            assert not _commit_called, "commit_code should not be called on test failure"
            assert not _wsl_called, "update_world_state should not be called on test failure"
