"""Tests for Task Graph Engine Temporal activities."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from task_graph_engine.temporal.activities import (
    check_budget,
    decompose_spec,
    execute_task,
    schedule_next_task,
    update_task_status,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(*, modules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a minimal spec dict for decomposition."""
    return {
        "name": "test-project",
        "description": "A test project",
        "modules": modules
        or [
            {"name": "auth", "description": "Authentication module"},
            {"name": "api", "description": "REST API module"},
        ],
    }


# ---------------------------------------------------------------------------
# decompose_spec
# ---------------------------------------------------------------------------


class TestDecomposeSpec:
    """Tests for the decompose_spec activity."""

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_returns_serialised_task_dicts(self, _mock_activity: MagicMock) -> None:
        """decompose_spec should return a list of JSON-serialisable dicts."""
        spec = _make_spec()

        result = await decompose_spec(spec)

        assert isinstance(result, list)
        assert len(result) > 0
        # Each module produces impl + test + review = 3 tasks.
        assert len(result) == 6  # 2 modules * 3 tasks each

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_tasks_contain_required_keys(self, _mock_activity: MagicMock) -> None:
        """Each returned dict should have id, type, status, dependencies."""
        spec = _make_spec(modules=[{"name": "core", "description": "Core"}])
        result = await decompose_spec(spec)

        for task_dict in result:
            assert "id" in task_dict
            assert "type" in task_dict
            assert "status" in task_dict
            assert "dependencies" in task_dict

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_dependency_chain_is_valid(self, _mock_activity: MagicMock) -> None:
        """Test tasks should depend on impl tasks, review on both."""
        spec = _make_spec(modules=[{"name": "single", "description": "One module"}])
        result = await decompose_spec(spec)

        # 3 tasks: impl, test, review
        assert len(result) == 3

        impl_task = result[0]
        test_task = result[1]
        review_task = result[2]

        # Impl has no dependencies.
        assert impl_task["dependencies"] == []

        # Test depends on impl.
        assert impl_task["id"] in test_task["dependencies"]

        # Review depends on both impl and test.
        assert impl_task["id"] in review_task["dependencies"]
        assert test_task["id"] in review_task["dependencies"]

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_empty_modules_creates_single_group(self, _mock_activity: MagicMock) -> None:
        """When spec has no modules, decomposer treats the whole spec as one."""
        spec = {"name": "bare", "description": "No modules key"}
        result = await decompose_spec(spec)

        # 1 implicit module -> 3 tasks.
        assert len(result) == 3


# ---------------------------------------------------------------------------
# schedule_next_task
# ---------------------------------------------------------------------------


class TestScheduleNextTask:
    """Tests for the schedule_next_task activity."""

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_returns_none_when_no_tasks_ready(self, mock_activity: MagicMock) -> None:
        """Current implementation always returns None."""
        mock_activity.heartbeat = MagicMock()

        result = await schedule_next_task()

        assert result is None
        mock_activity.heartbeat.assert_called_once()


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


class TestUpdateTaskStatus:
    """Tests for the update_task_status activity."""

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_heartbeats_with_task_info(self, mock_activity: MagicMock) -> None:
        """Activity should heartbeat with task_id and status."""
        mock_activity.heartbeat = MagicMock()

        await update_task_status("task-abc123", "running")

        mock_activity.heartbeat.assert_called_once_with("updating task-abc123 to running")

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_does_not_raise(self, mock_activity: MagicMock) -> None:
        """Activity is a no-op placeholder but should not raise."""
        mock_activity.heartbeat = MagicMock()

        # Should complete without error for any status.
        await update_task_status("task-000", "pending")
        await update_task_status("task-000", "completed")
        await update_task_status("task-000", "failed")


# ---------------------------------------------------------------------------
# execute_task
# ---------------------------------------------------------------------------


class TestExecuteTask:
    """Tests for the execute_task activity."""

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_returns_pass_verdict(self, mock_activity: MagicMock) -> None:
        """Placeholder always returns pass verdict."""
        mock_activity.heartbeat = MagicMock()
        task = {"id": "task-test001", "type": "implement_feature"}

        result = await execute_task(task)

        assert result["verdict"] == "pass"
        assert result["task_id"] == "task-test001"

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_handles_missing_id_gracefully(self, mock_activity: MagicMock) -> None:
        """When task dict has no id, it should use 'unknown'."""
        mock_activity.heartbeat = MagicMock()
        result = await execute_task({})

        assert result["task_id"] == "unknown"
        assert result["verdict"] == "pass"

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_returns_tokens_consumed(self, mock_activity: MagicMock) -> None:
        """Result should include tokens_consumed key."""
        mock_activity.heartbeat = MagicMock()
        result = await execute_task({"id": "task-x", "type": "fix_bug"})

        assert "tokens_consumed" in result
        assert isinstance(result["tokens_consumed"], int)


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


class TestCheckBudget:
    """Tests for the check_budget activity."""

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_returns_budget_not_exhausted(self, mock_activity: MagicMock) -> None:
        """Placeholder returns budget not exhausted."""
        mock_activity.heartbeat = MagicMock()

        result = await check_budget()

        assert result["exhausted"] is False
        assert result["consumed_pct"] == 0.0
        assert result["remaining_tokens"] == 10_000_000

    @patch("task_graph_engine.temporal.activities.activity")
    async def test_budget_result_has_required_keys(self, mock_activity: MagicMock) -> None:
        """Result should have exhausted, consumed_pct, remaining_tokens."""
        mock_activity.heartbeat = MagicMock()

        result = await check_budget()

        assert "exhausted" in result
        assert "consumed_pct" in result
        assert "remaining_tokens" in result
