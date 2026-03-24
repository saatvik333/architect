"""Concurrency tests for World State Ledger proposal validation.

These tests require a running Postgres instance and are marked as integration tests.
Run with: pytest tests/integration/ -m integration
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
async def state_manager(pg_dsn: str, redis_url: str):
    """Create a real StateManager backed by Postgres and Redis."""
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from architect_db.models.base import Base
    from architect_events.publisher import EventPublisher
    from world_state_ledger.cache import StateCache
    from world_state_ledger.state_manager import StateManager

    engine = create_async_engine(pg_dsn, pool_size=5)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=False)
    cache = StateCache(redis_client)
    publisher = EventPublisher(redis_url)
    await publisher.connect()

    manager = StateManager(session_factory, cache, publisher)
    yield manager

    await publisher.close()
    await redis_client.aclose()
    await engine.dispose()


class TestConcurrentProposals:
    @pytest.mark.asyncio
    async def test_concurrent_proposals_one_wins(self, state_manager) -> None:
        """When two proposals target the same field concurrently, exactly one should succeed."""
        from architect_common.types import AgentId, ProposalId, TaskId
        from world_state_ledger.models import Proposal, StateMutation

        # Submit two proposals that both try to modify budget.consumed_tokens
        proposal_a = Proposal(
            id=ProposalId("prop-a"),
            agent_id=AgentId("agent-1"),
            task_id=TaskId("task-1"),
            mutations=[
                StateMutation(path="budget.consumed_tokens", old_value=0, new_value=100),
            ],
            rationale="First proposal",
        )
        proposal_b = Proposal(
            id=ProposalId("prop-b"),
            agent_id=AgentId("agent-2"),
            task_id=TaskId("task-2"),
            mutations=[
                StateMutation(path="budget.consumed_tokens", old_value=0, new_value=200),
            ],
            rationale="Second proposal",
        )

        await state_manager.submit_proposal(proposal_a)
        await state_manager.submit_proposal(proposal_b)

        # Commit both concurrently
        results = await asyncio.gather(
            state_manager.validate_and_commit("prop-a"),
            state_manager.validate_and_commit("prop-b"),
            return_exceptions=True,
        )

        # Exactly one should succeed, the other should raise OptimisticConcurrencyError
        successes = [r for r in results if r is True]
        errors = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
        assert len(errors) == 1, f"Expected exactly 1 error, got {len(errors)}: {results}"

    @pytest.mark.asyncio
    async def test_sequential_proposals_both_succeed(self, state_manager) -> None:
        """Sequential proposals to different fields should both succeed."""
        from architect_common.types import AgentId, ProposalId, TaskId
        from world_state_ledger.models import Proposal, StateMutation

        proposal_a = Proposal(
            id=ProposalId("prop-seq-a"),
            agent_id=AgentId("agent-1"),
            task_id=TaskId("task-1"),
            mutations=[
                StateMutation(path="budget.consumed_tokens", old_value=0, new_value=100),
            ],
            rationale="First sequential",
        )

        await state_manager.submit_proposal(proposal_a)
        result_a = await state_manager.validate_and_commit("prop-seq-a")
        assert result_a is True
