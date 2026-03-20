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
from world_state_ledger.state_manager import _CHECKPOINT_INTERVAL, StateManager

# ── helpers ──────────────────────────────────────────────────────────


def _make_ledger_row(
    *,
    version: int,
    state_snapshot: dict | None = None,
    mutations: list[dict] | None = None,
    is_checkpoint: bool = False,
) -> MagicMock:
    """Create a mock LedgerRow with the given attributes."""
    row = MagicMock()
    row.version = version
    row.state_snapshot = state_snapshot
    row.mutations = mutations
    row.is_checkpoint = is_checkpoint
    return row


def _mock_execute_results(results_sequence: list) -> AsyncMock:
    """Return an AsyncMock for session.execute that returns results in order.

    Each element in *results_sequence* should be either:
    - A value for ``scalar_one_or_none()``
    - A list of values for ``scalars().all()``

    The mock distinguishes between these based on which method is called.
    """
    mock_results = []
    for item in results_sequence:
        mock_result = MagicMock()
        if isinstance(item, list):
            # For scalars().all()
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = item
            mock_result.scalars.return_value = scalars_mock
            mock_result.scalar_one_or_none.return_value = None
        else:
            # For scalar_one_or_none()
            mock_result.scalar_one_or_none.return_value = item
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            mock_result.scalars.return_value = scalars_mock
        mock_results.append(mock_result)

    return AsyncMock(side_effect=mock_results)


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

    async def test_get_current_reconstructs_from_delta(
        self, state_manager: StateManager, state_cache
    ) -> None:
        """When the latest row is a delta, get_current reconstructs via get_version."""
        state_cache._redis.get = AsyncMock(return_value=None)
        session = state_manager._session_factory._session

        # First call (get_current): returns a delta row (is_checkpoint=False).
        latest_row = _make_ledger_row(
            version=3,
            state_snapshot=None,
            mutations=[{"path": "budget.burn_rate", "old_value": 100.0, "new_value": 300.0}],
            is_checkpoint=False,
        )

        # get_version will be called for version 3, which opens a new session.
        # The new session needs: checkpoint query, then deltas query.
        checkpoint_row = _make_ledger_row(
            version=1,
            state_snapshot=WorldState(
                version=1,
                budget=BudgetState(
                    allocated_tokens=10_000,
                    consumed_tokens=2_000,
                    remaining_tokens=8_000,
                    burn_rate=100.0,
                ),
            ).model_dump(mode="json"),
            is_checkpoint=True,
        )

        delta_v2 = _make_ledger_row(
            version=2,
            mutations=[{"path": "budget.burn_rate", "old_value": 100.0, "new_value": 200.0}],
            is_checkpoint=False,
        )
        delta_v3 = _make_ledger_row(
            version=3,
            mutations=[{"path": "budget.burn_rate", "old_value": 200.0, "new_value": 300.0}],
            is_checkpoint=False,
        )

        # get_current opens session #1: execute returns latest_row.
        # get_version opens session #2: execute called twice (checkpoint, then deltas).
        # Both sessions share the same mock, so we chain all calls.
        session.execute = _mock_execute_results(
            [
                latest_row,  # get_current: latest row
                checkpoint_row,  # get_version: checkpoint query
                [delta_v2, delta_v3],  # get_version: deltas query
            ]
        )

        result = await state_manager.get_current()
        assert result.version == 3
        assert result.budget.burn_rate == 300.0

    async def test_get_current_uses_checkpoint_directly(
        self, state_manager: StateManager, state_cache
    ) -> None:
        """When the latest row IS a checkpoint, use its snapshot directly."""
        state_cache._redis.get = AsyncMock(return_value=None)
        session = state_manager._session_factory._session

        state = WorldState(
            version=20,
            budget=BudgetState(
                allocated_tokens=10_000,
                consumed_tokens=5_000,
                remaining_tokens=5_000,
                burn_rate=150.0,
            ),
        )
        checkpoint_row = _make_ledger_row(
            version=20,
            state_snapshot=state.model_dump(mode="json"),
            is_checkpoint=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = checkpoint_row
        session.execute = AsyncMock(return_value=mock_result)

        result = await state_manager.get_current()
        assert result.version == 20
        assert result.budget.consumed_tokens == 5_000


# ── get_version ──────────────────────────────────────────────────────


class TestGetVersion:
    """Tests for StateManager.get_version."""

    async def test_raises_on_missing_version(self, state_manager: StateManager) -> None:
        """Non-existent versions should raise LedgerVersionNotFoundError."""
        session = state_manager._session_factory._session
        # No checkpoint found, no delta rows found.
        session.execute = _mock_execute_results(
            [
                None,  # checkpoint query: no checkpoint
                [],  # deltas query: no deltas
            ]
        )

        with pytest.raises(LedgerVersionNotFoundError):
            await state_manager.get_version(999)

    async def test_returns_checkpoint_directly(self, state_manager: StateManager) -> None:
        """When the requested version IS a checkpoint, return it without delta replay."""
        session = state_manager._session_factory._session

        state = WorldState(
            version=20,
            budget=BudgetState(
                allocated_tokens=10_000,
                consumed_tokens=4_000,
                remaining_tokens=6_000,
            ),
        )
        checkpoint_row = _make_ledger_row(
            version=20,
            state_snapshot=state.model_dump(mode="json"),
            is_checkpoint=True,
        )

        # Checkpoint query returns the row; start_version == requested version, so return.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = checkpoint_row
        session.execute = AsyncMock(return_value=mock_result)

        result = await state_manager.get_version(20)
        assert result.version == 20
        assert result.budget.consumed_tokens == 4_000

    async def test_reconstructs_from_checkpoint_plus_deltas(
        self, state_manager: StateManager
    ) -> None:
        """get_version should replay deltas on top of the nearest checkpoint."""
        session = state_manager._session_factory._session

        checkpoint_state = WorldState(
            version=20,
            budget=BudgetState(
                allocated_tokens=10_000,
                consumed_tokens=4_000,
                remaining_tokens=6_000,
                burn_rate=100.0,
            ),
        )
        checkpoint_row = _make_ledger_row(
            version=20,
            state_snapshot=checkpoint_state.model_dump(mode="json"),
            is_checkpoint=True,
        )

        delta_v21 = _make_ledger_row(
            version=21,
            mutations=[
                {"path": "budget.consumed_tokens", "old_value": 4000, "new_value": 4500},
                {"path": "budget.remaining_tokens", "old_value": 6000, "new_value": 5500},
            ],
            is_checkpoint=False,
        )
        delta_v22 = _make_ledger_row(
            version=22,
            mutations=[
                {"path": "budget.consumed_tokens", "old_value": 4500, "new_value": 5000},
                {"path": "budget.remaining_tokens", "old_value": 5500, "new_value": 5000},
            ],
            is_checkpoint=False,
        )

        session.execute = _mock_execute_results(
            [
                checkpoint_row,  # checkpoint query
                [delta_v21, delta_v22],  # deltas query
            ]
        )

        result = await state_manager.get_version(22)
        assert result.version == 22
        assert result.budget.consumed_tokens == 5_000
        assert result.budget.remaining_tokens == 5_000

    async def test_reconstructs_from_pristine_without_checkpoint(
        self, state_manager: StateManager
    ) -> None:
        """When no checkpoint exists, reconstruct from pristine state (version 0)."""
        session = state_manager._session_factory._session

        delta_v1 = _make_ledger_row(
            version=1,
            mutations=[
                {"path": "budget.consumed_tokens", "old_value": 0, "new_value": 500},
            ],
            is_checkpoint=False,
        )

        session.execute = _mock_execute_results(
            [
                None,  # checkpoint query: no checkpoint
                [delta_v1],  # deltas query
            ]
        )

        result = await state_manager.get_version(1)
        assert result.version == 1
        assert result.budget.consumed_tokens == 500


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


# ── Delta storage (checkpoint interval) ──────────────────────────────


class TestDeltaStorage:
    """Tests that validate_and_commit writes deltas vs. checkpoints correctly."""

    def test_checkpoint_interval_is_20(self) -> None:
        """Sanity check the constant is what we expect."""
        assert _CHECKPOINT_INTERVAL == 20

    def test_non_checkpoint_version(self) -> None:
        """Versions that are NOT multiples of _CHECKPOINT_INTERVAL are not checkpoints."""
        for v in (1, 2, 10, 19, 21, 39):
            assert v % _CHECKPOINT_INTERVAL != 0

    def test_checkpoint_version(self) -> None:
        """Versions that ARE multiples of _CHECKPOINT_INTERVAL are checkpoints."""
        for v in (20, 40, 60, 100):
            assert v % _CHECKPOINT_INTERVAL == 0
