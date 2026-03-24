"""Tests for World State Ledger Temporal activities."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from architect_common.types import AgentId, TaskId, new_proposal_id
from world_state_ledger.event_log import EventLog
from world_state_ledger.models import (
    BudgetState,
    Proposal,
    StateMutation,
    WorldState,
)
from world_state_ledger.state_manager import StateManager
from world_state_ledger.temporal.activities import WSLActivities

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_state_manager() -> AsyncMock:
    """Return a mock StateManager."""
    mgr = AsyncMock(spec=StateManager)
    return mgr


@pytest.fixture()
def mock_event_log() -> AsyncMock:
    """Return a mock EventLog."""
    return AsyncMock(spec=EventLog)


@pytest.fixture()
def wsl_activities(mock_state_manager: AsyncMock, mock_event_log: AsyncMock) -> WSLActivities:
    """Build a WSLActivities with mocked dependencies."""
    return WSLActivities(
        state_manager=mock_state_manager,
        event_log=mock_event_log,
    )


def _sample_world_state(**overrides: Any) -> WorldState:
    """Build a minimal WorldState for test assertions."""
    defaults: dict[str, Any] = {
        "version": 1,
        "budget": BudgetState(
            allocated_tokens=10_000,
            consumed_tokens=2_000,
            remaining_tokens=8_000,
            burn_rate=100.0,
        ),
    }
    defaults.update(overrides)
    return WorldState(**defaults)


def _sample_proposal(**overrides: Any) -> dict[str, Any]:
    """Build a Proposal dict for submit_proposal input."""
    proposal = Proposal(
        id=overrides.get("id", new_proposal_id()),
        agent_id=AgentId(overrides.get("agent_id", "agent-test123456")),
        task_id=TaskId(overrides.get("task_id", "task-test123456")),
        mutations=overrides.get(
            "mutations",
            [
                StateMutation(
                    path="budget.consumed_tokens",
                    old_value=2000,
                    new_value=2500,
                ),
            ],
        ),
        rationale=overrides.get("rationale", "Test mutation"),
    )
    return proposal.model_dump(mode="json")


# ---------------------------------------------------------------------------
# get_current_state
# ---------------------------------------------------------------------------


class TestGetCurrentState:
    """Tests for the get_current_state activity."""

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_returns_serialised_world_state(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """get_current_state should return a dict from state_manager.get_current()."""
        state = _sample_world_state()
        mock_state_manager.get_current.return_value = state

        result = await wsl_activities.get_current_state()

        assert isinstance(result, dict)
        assert result["version"] == 1
        assert result["budget"]["allocated_tokens"] == 10_000
        mock_state_manager.get_current.assert_awaited_once()

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_returns_pristine_state_on_empty_ledger(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """When ledger is empty, should return version=0 pristine state."""
        pristine = WorldState()  # version 0, all defaults
        mock_state_manager.get_current.return_value = pristine

        result = await wsl_activities.get_current_state()

        assert result["version"] == 0

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_contains_all_state_sections(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """Returned dict should include budget, agents, infra, etc."""
        state = _sample_world_state()
        mock_state_manager.get_current.return_value = state

        result = await wsl_activities.get_current_state()

        assert "budget" in result
        assert "agents" in result
        assert "infra" in result
        assert "build" in result


# ---------------------------------------------------------------------------
# submit_proposal
# ---------------------------------------------------------------------------


class TestSubmitProposal:
    """Tests for the submit_proposal activity."""

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_returns_proposal_id_string(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """submit_proposal should return the proposal ID as a string."""
        mock_state_manager.submit_proposal.return_value = "prop-abc12345"

        proposal_data = _sample_proposal()
        result = await wsl_activities.submit_proposal(proposal_data)

        assert isinstance(result, str)
        assert result == "prop-abc12345"

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_passes_validated_proposal_to_manager(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """The proposal dict should be validated into a Proposal model."""
        mock_state_manager.submit_proposal.return_value = "prop-xyz"

        proposal_data = _sample_proposal(
            agent_id="agent-custom00001",
            task_id="task-custom00001",
            rationale="Custom rationale",
        )
        await wsl_activities.submit_proposal(proposal_data)

        # Verify submit_proposal was called with a Proposal instance
        call_args = mock_state_manager.submit_proposal.call_args
        submitted = call_args[0][0]
        assert isinstance(submitted, Proposal)
        assert str(submitted.agent_id) == "agent-custom00001"
        assert str(submitted.task_id) == "task-custom00001"

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_propagates_validation_error(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
    ) -> None:
        """Invalid proposal data should raise a Pydantic ValidationError."""
        from pydantic import ValidationError

        # Missing required fields (agent_id, task_id)
        with pytest.raises(ValidationError):
            await wsl_activities.submit_proposal({"bad": "data"})


# ---------------------------------------------------------------------------
# validate_and_commit
# ---------------------------------------------------------------------------


class TestValidateAndCommit:
    """Tests for the validate_and_commit activity."""

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_returns_true_on_accepted(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """validate_and_commit should return True when proposal is accepted."""
        mock_state_manager.validate_and_commit.return_value = True

        result = await wsl_activities.validate_and_commit("prop-accept01")

        assert result is True
        mock_state_manager.validate_and_commit.assert_awaited_once_with("prop-accept01")

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_returns_false_on_rejected(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """validate_and_commit should return False when proposal is rejected."""
        mock_state_manager.validate_and_commit.return_value = False

        result = await wsl_activities.validate_and_commit("prop-reject01")

        assert result is False

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_propagates_concurrency_error(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """OptimisticConcurrencyError from state_manager should propagate."""
        from architect_common.errors import OptimisticConcurrencyError

        mock_state_manager.validate_and_commit.side_effect = OptimisticConcurrencyError(
            "version conflict",
            details={"expected": 1, "actual": 2},
        )

        with pytest.raises(OptimisticConcurrencyError, match="version conflict"):
            await wsl_activities.validate_and_commit("prop-conflict01")

    @patch("world_state_ledger.temporal.activities.activity")
    async def test_propagates_version_not_found_error(
        self,
        mock_activity: MagicMock,
        wsl_activities: WSLActivities,
        mock_state_manager: AsyncMock,
    ) -> None:
        """LedgerVersionNotFoundError from state_manager should propagate."""
        from architect_common.errors import LedgerVersionNotFoundError

        mock_state_manager.validate_and_commit.side_effect = LedgerVersionNotFoundError(
            "proposal not found",
            details={"proposal_id": "prop-missing"},
        )

        with pytest.raises(LedgerVersionNotFoundError, match="proposal not found"):
            await wsl_activities.validate_and_commit("prop-missing")
