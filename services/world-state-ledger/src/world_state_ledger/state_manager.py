"""Core state management logic for the World State Ledger."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import EventType, ProposalVerdict
from architect_common.errors import (
    LedgerVersionNotFoundError,
)
from architect_common.logging import get_logger
from architect_common.types import LedgerVersion, utcnow
from architect_db.models.ledger import WorldStateLedger as LedgerRow
from architect_db.models.proposal import Proposal as ProposalRow
from architect_events.publisher import EventPublisher
from architect_events.schemas import EventEnvelope
from world_state_ledger.cache import StateCache
from world_state_ledger.models import Proposal, StateMutation, WorldState

logger = get_logger(component="world_state_ledger.state_manager")


class StateManager:
    """Manages the lifecycle of world state: reads, proposals, and commits.

    This is the heart of Component #2 — every state mutation flows through here.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cache: StateCache,
        event_publisher: EventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._cache = cache
        self._event_publisher = event_publisher

    # ── Reads ────────────────────────────────────────────────────────

    async def get_current(self) -> WorldState:
        """Return the latest world state snapshot.

        Reads from the Redis cache first; falls back to DB on cache miss.
        """
        cached = await self._cache.get_current_state()
        if cached is not None:
            logger.debug("cache hit")
            return WorldState.model_validate(cached)

        logger.debug("cache miss — loading from db")
        async with self._session_factory() as session:
            stmt = select(LedgerRow).order_by(LedgerRow.version.desc()).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            # No state yet — return a pristine world state.
            state = WorldState()
            await self._cache.set_current_state(state.model_dump(mode="json"), state.version)
            return state

        state = WorldState.model_validate(row.state_snapshot)
        await self._cache.set_current_state(state.model_dump(mode="json"), state.version)
        return state

    async def get_version(self, version: int) -> WorldState:
        """Return a specific historical version of the world state.

        Raises:
            LedgerVersionNotFoundError: If the requested version does not exist.
        """
        async with self._session_factory() as session:
            row = await session.get(LedgerRow, version)

        if row is None:
            raise LedgerVersionNotFoundError(
                f"Ledger version {version} not found",
                details={"version": version},
            )

        return WorldState.model_validate(row.state_snapshot)

    # ── Proposal lifecycle ───────────────────────────────────────────

    async def submit_proposal(self, proposal: Proposal) -> str:
        """Persist a new proposal and publish a creation event.

        Returns:
            The proposal ID as a string.
        """
        current_state = await self.get_current()

        async with self._session_factory() as session:
            row = ProposalRow(
                id=str(proposal.id),
                agent_id=str(proposal.agent_id),
                task_id=str(proposal.task_id),
                mutations=[m.model_dump(mode="json") for m in proposal.mutations],
                rationale=proposal.rationale,
                verdict=ProposalVerdict.PENDING.value,
                ledger_version_before=current_state.version,
            )
            session.add(row)
            await session.commit()

        # Publish event.
        await self._event_publisher.publish(
            EventEnvelope(
                type=EventType.PROPOSAL_CREATED,
                payload={
                    "proposal_id": str(proposal.id),
                    "agent_id": str(proposal.agent_id),
                    "task_id": str(proposal.task_id),
                    "mutation_count": len(proposal.mutations),
                },
            )
        )

        logger.info(
            "proposal submitted",
            proposal_id=str(proposal.id),
            mutations=len(proposal.mutations),
        )
        return str(proposal.id)

    async def validate_and_commit(self, proposal_id: str) -> bool:
        """Validate a pending proposal and, if valid, atomically commit it.

        Returns:
            ``True`` if the proposal was accepted and committed, ``False`` if rejected.

        Raises:
            LedgerVersionNotFoundError: If the proposal references a missing version.
            OptimisticConcurrencyError: If the ledger moved forward since the proposal.
        """
        # 1. Load proposal from DB.
        async with self._session_factory() as session:
            proposal_row = await session.get(ProposalRow, proposal_id)

        if proposal_row is None:
            raise LedgerVersionNotFoundError(
                f"Proposal {proposal_id} not found",
                details={"proposal_id": proposal_id},
            )

        if proposal_row.verdict != ProposalVerdict.PENDING.value:
            logger.warning("proposal already resolved", proposal_id=proposal_id)
            return proposal_row.verdict == ProposalVerdict.ACCEPTED.value

        mutations = [StateMutation.model_validate(m) for m in (proposal_row.mutations or [])]

        # 2. Load current state.
        current_state = await self.get_current()

        # 3. Validate mutations.
        valid, rejection_reason = self._validate_mutations(current_state, mutations)

        now = utcnow()

        if not valid:
            # Mark rejected.
            async with self._session_factory() as session:
                row = await session.get(ProposalRow, proposal_id)
                if row is not None:
                    row.verdict = ProposalVerdict.REJECTED.value
                    row.verdict_reason = rejection_reason
                    row.verdict_at = now
                    await session.commit()

            await self._event_publisher.publish(
                EventEnvelope(
                    type=EventType.PROPOSAL_REJECTED,
                    payload={
                        "proposal_id": proposal_id,
                        "reason": rejection_reason or "validation failed",
                    },
                )
            )
            logger.info("proposal rejected", proposal_id=proposal_id, reason=rejection_reason)
            return False

        # 4. Apply mutations and create new ledger version.
        new_state = self._apply_mutations(current_state, mutations)
        new_version = LedgerVersion(current_state.version + 1)
        new_state.version = new_version
        new_state.updated_at = now

        async with self._session_factory() as session:
            # Write new ledger snapshot.
            ledger_row = LedgerRow(
                version=new_version,
                state_snapshot=new_state.model_dump(mode="json"),
                updated_at=now,
                proposal_id=proposal_id,
            )
            session.add(ledger_row)

            # Update proposal verdict.
            prop_row = await session.get(ProposalRow, proposal_id)
            if prop_row is not None:
                prop_row.verdict = ProposalVerdict.ACCEPTED.value
                prop_row.verdict_at = now
                prop_row.ledger_version_after = new_version

            await session.commit()

        # 5. Update cache.
        await self._cache.set_current_state(new_state.model_dump(mode="json"), new_version)

        # 6. Publish accepted event.
        await self._event_publisher.publish(
            EventEnvelope(
                type=EventType.PROPOSAL_ACCEPTED,
                payload={
                    "proposal_id": proposal_id,
                    "ledger_version": new_version,
                },
            )
        )
        await self._event_publisher.publish(
            EventEnvelope(
                type=EventType.LEDGER_UPDATED,
                payload={
                    "version": new_version,
                    "proposal_id": proposal_id,
                },
            )
        )

        logger.info(
            "proposal committed",
            proposal_id=proposal_id,
            new_version=new_version,
        )
        return True

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _apply_mutations(state: WorldState, mutations: list[StateMutation]) -> WorldState:
        """Apply a list of mutations to the world state and return a new copy.

        Mutations use dot-paths (e.g. ``"budget.consumed_tokens"``) to address
        nested fields.  We serialise to dict, apply changes, and reparse.
        """
        data = state.model_dump(mode="json")

        for mutation in mutations:
            parts = mutation.path.split(".")
            target = data
            for part in parts[:-1]:
                if isinstance(target, dict):
                    target = target.setdefault(part, {})
                else:
                    break
            if isinstance(target, dict) and parts:
                target[parts[-1]] = mutation.new_value

        return WorldState.model_validate(data)

    @staticmethod
    def _validate_mutations(
        state: WorldState, mutations: list[StateMutation]
    ) -> tuple[bool, str | None]:
        """Check that every mutation's ``old_value`` matches the current state.

        Also enforces basic budget constraints:
        - ``budget.remaining_tokens`` must not drop below zero.

        Returns:
            A ``(valid, reason)`` tuple where *reason* is ``None`` when valid.
        """
        data = state.model_dump(mode="json")

        for mutation in mutations:
            parts = mutation.path.split(".")
            current: Any = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                    break

            # Optimistic concurrency check: old_value must match current.
            if mutation.old_value is not None and current != mutation.old_value:
                return (
                    False,
                    f"Stale value at '{mutation.path}': "
                    f"expected {mutation.old_value!r}, got {current!r}",
                )

        # Budget constraint: simulate the final remaining_tokens value.
        simulated = state.model_dump(mode="json")
        for mutation in mutations:
            parts = mutation.path.split(".")
            target = simulated
            for part in parts[:-1]:
                if isinstance(target, dict):
                    target = target.setdefault(part, {})
                else:
                    break
            if isinstance(target, dict) and parts:
                target[parts[-1]] = mutation.new_value

        remaining = simulated.get("budget", {}).get("remaining_tokens", 0)
        if isinstance(remaining, (int, float)) and remaining < 0:
            return (
                False,
                f"Budget constraint violated: remaining_tokens would be {remaining}",
            )

        return (True, None)
