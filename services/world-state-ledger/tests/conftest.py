"""Shared fixtures for the World State Ledger test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.types import AgentId, TaskId, new_proposal_id
from architect_events.publisher import EventPublisher
from world_state_ledger.cache import StateCache
from world_state_ledger.models import (
    BudgetState,
    Proposal,
    StateMutation,
    WorldState,
)
from world_state_ledger.state_manager import StateManager

# ── Mock factories ───────────────────────────────────────────────────


@pytest.fixture()
def mock_session_factory() -> AsyncMock:
    """Return a mock async session factory.

    The factory itself is an AsyncMock; the session it yields is also an
    AsyncMock whose ``get``, ``execute``, ``add``, ``commit``, and
    ``rollback`` methods are all async.
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()

    # Create an async context manager that yields the session
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=ctx)
    factory._session = session  # expose for assertions
    return factory


@pytest.fixture()
def mock_redis() -> AsyncMock:
    """Return a mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.ttl = AsyncMock(return_value=200)
    pipe = AsyncMock()
    pipe.set = MagicMock()
    pipe.execute = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


@pytest.fixture()
def state_cache(mock_redis: AsyncMock) -> StateCache:
    """Return a StateCache backed by a mock Redis client."""
    return StateCache(mock_redis)


@pytest.fixture()
def mock_event_publisher() -> AsyncMock:
    """Return a mock EventPublisher with an async publish method."""
    pub = AsyncMock(spec=EventPublisher)
    pub.publish = AsyncMock(return_value="mock-mid")
    return pub


@pytest.fixture()
def state_manager(
    mock_session_factory: AsyncMock,
    state_cache: StateCache,
    mock_event_publisher: AsyncMock,
) -> StateManager:
    """Return a StateManager wired to mocked dependencies."""
    return StateManager(mock_session_factory, state_cache, mock_event_publisher)


@pytest.fixture()
def sample_world_state() -> WorldState:
    """Return a minimal valid WorldState for testing."""
    return WorldState(
        version=1,
        budget=BudgetState(
            allocated_tokens=10_000,
            consumed_tokens=2_000,
            remaining_tokens=8_000,
            burn_rate=100.0,
        ),
    )


@pytest.fixture()
def sample_proposal() -> Proposal:
    """Return a simple proposal with one mutation."""
    return Proposal(
        id=new_proposal_id(),
        agent_id=AgentId("agent-test123456"),
        task_id=TaskId("task-test123456"),
        mutations=[
            StateMutation(
                path="budget.consumed_tokens",
                old_value=2000,
                new_value=2500,
            ),
            StateMutation(
                path="budget.remaining_tokens",
                old_value=8000,
                new_value=7500,
            ),
        ],
        rationale="Consumed 500 tokens for task execution.",
    )
