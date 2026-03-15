"""Unit tests for the StateManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.errors import LedgerVersionNotFoundError
from world_state_ledger.models import (
    BudgetState,
    Proposal,
    StateMutation,
    WorldState,
)
from world_state_ledger.state_manager import StateManager

# ── get_current ──────────────────────────────────────────────────────


class TestGetCurrent:
    """Tests for StateManager.get_current."""

    async def test_returns_state_from_cache(
        self, state_manager: StateManager, state_cache, sample_world_state: WorldState
    ) -> None:
        """When the cache has data, it should be returned directly."""
        state_cache._redis.get = AsyncMock(
            return_value=sample_world_state.model_dump_json().encode()
        )
        state_cache._redis.ttl = AsyncMock(return_value=200)
        result = await state_manager.get_current()
        assert result.version == sample_world_state.version

    async def test_returns_pristine_state_on_empty_db(
        self, state_manager: StateManager, state_cache
    ) -> None:
        """When both cache and DB are empty, a pristine WorldState is returned."""
        # Cache miss.
        state_cache._redis.get = AsyncMock(return_value=None)
        # DB miss — session.execute returns empty result.
        session = state_manager._session_factory._session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await state_manager.get_current()
        assert result.version == 0


# ── get_version ──────────────────────────────────────────────────────


class TestGetVersion:
    """Tests for StateManager.get_version."""

    async def test_raises_on_missing_version(self, state_manager: StateManager) -> None:
        """Non-existent versions should raise LedgerVersionNotFoundError."""
        session = state_manager._session_factory._session
        session.get = AsyncMock(return_value=None)

        with pytest.raises(LedgerVersionNotFoundError):
            await state_manager.get_version(999)


# ── _validate_mutations ──────────────────────────────────────────────


class TestValidateMutations:
    """Tests for the private _validate_mutations helper."""

    def test_passes_when_old_values_match(self, sample_world_state: WorldState) -> None:
        mutations = [
            StateMutation(path="budget.consumed_tokens", old_value=2000, new_value=3000),
            StateMutation(path="budget.remaining_tokens", old_value=8000, new_value=7000),
        ]
        valid, reason = StateManager._validate_mutations(sample_world_state, mutations)
        assert valid is True
        assert reason is None

    def test_rejects_stale_old_value(self, sample_world_state: WorldState) -> None:
        mutations = [
            StateMutation(
                path="budget.consumed_tokens",
                old_value=9999,  # does not match current (2000)
                new_value=3000,
            ),
        ]
        valid, reason = StateManager._validate_mutations(sample_world_state, mutations)
        assert valid is False
        assert reason is not None
        assert "Stale value" in reason

    def test_rejects_negative_remaining_tokens(self) -> None:
        state = WorldState(
            version=1,
            budget=BudgetState(
                allocated_tokens=1000,
                consumed_tokens=900,
                remaining_tokens=100,
            ),
        )
        mutations = [
            StateMutation(
                path="budget.remaining_tokens",
                old_value=100,
                new_value=-50,  # should fail budget constraint
            ),
        ]
        valid, reason = StateManager._validate_mutations(state, mutations)
        assert valid is False
        assert "Budget constraint" in (reason or "")

    def test_allows_mutations_without_old_value(self, sample_world_state: WorldState) -> None:
        """When old_value is None, skip the concurrency check."""
        mutations = [
            StateMutation(path="budget.burn_rate", old_value=None, new_value=200.0),
        ]
        valid, reason = StateManager._validate_mutations(sample_world_state, mutations)
        assert valid is True


# ── _apply_mutations ─────────────────────────────────────────────────


class TestApplyMutations:
    """Tests for the private _apply_mutations helper."""

    def test_applies_dot_path_mutations(self, sample_world_state: WorldState) -> None:
        mutations = [
            StateMutation(path="budget.consumed_tokens", old_value=2000, new_value=5000),
            StateMutation(path="budget.remaining_tokens", old_value=8000, new_value=5000),
        ]
        new_state = StateManager._apply_mutations(sample_world_state, mutations)
        assert new_state.budget.consumed_tokens == 5000
        assert new_state.budget.remaining_tokens == 5000

    def test_preserves_untouched_fields(self, sample_world_state: WorldState) -> None:
        mutations = [
            StateMutation(path="budget.burn_rate", old_value=100.0, new_value=200.0),
        ]
        new_state = StateManager._apply_mutations(sample_world_state, mutations)
        assert new_state.budget.burn_rate == 200.0
        # Unchanged fields should remain.
        assert new_state.budget.allocated_tokens == 10_000
        assert new_state.version == sample_world_state.version


# ── submit_proposal ──────────────────────────────────────────────────


class TestSubmitProposal:
    """Tests for StateManager.submit_proposal."""

    async def test_returns_proposal_id(
        self,
        state_manager: StateManager,
        state_cache,
        sample_proposal: Proposal,
        sample_world_state: WorldState,
    ) -> None:
        """submit_proposal should persist and return the proposal ID."""
        # Make get_current return our sample state.
        state_cache._redis.get = AsyncMock(
            return_value=sample_world_state.model_dump_json().encode()
        )

        result = await state_manager.submit_proposal(sample_proposal)
        assert result == str(sample_proposal.id)

    async def test_publishes_event(
        self,
        state_manager: StateManager,
        state_cache,
        mock_event_publisher: AsyncMock,
        sample_proposal: Proposal,
        sample_world_state: WorldState,
    ) -> None:
        """submit_proposal should publish a PROPOSAL_CREATED event."""
        state_cache._redis.get = AsyncMock(
            return_value=sample_world_state.model_dump_json().encode()
        )

        await state_manager.submit_proposal(sample_proposal)
        mock_event_publisher.publish.assert_called_once()
        envelope = mock_event_publisher.publish.call_args[0][0]
        assert envelope.type.value == "proposal.created"
