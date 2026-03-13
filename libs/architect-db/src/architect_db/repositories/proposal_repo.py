"""Proposal repository with domain-specific query methods."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from architect_common.enums import ProposalVerdict
from architect_common.types import ProposalId, TaskId
from architect_db.models.proposal import Proposal
from architect_db.repositories.base import BaseRepository


class ProposalRepository(BaseRepository[Proposal]):
    """Async repository for :class:`Proposal` entities."""

    model_class = Proposal

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        """Return the proposal with the given ID, or ``None``.

        Args:
            proposal_id: The proposal primary key.
        """
        return await self._session.get(Proposal, str(proposal_id))

    async def get_pending(self) -> list[Proposal]:
        """Return all proposals with a ``pending`` verdict.

        Returns:
            A list of pending :class:`Proposal` rows ordered by creation time.
        """
        stmt = (
            select(Proposal)
            .where(Proposal.verdict == ProposalVerdict.PENDING)
            .order_by(Proposal.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_task(self, task_id: TaskId) -> list[Proposal]:
        """Return all proposals associated with a given task.

        Args:
            task_id: The task primary key.

        Returns:
            A list of :class:`Proposal` rows for the task.
        """
        stmt = (
            select(Proposal)
            .where(Proposal.task_id == str(task_id))
            .order_by(Proposal.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_verdict(
        self,
        proposal_id: ProposalId,
        verdict: ProposalVerdict,
    ) -> Proposal:
        """Update the verdict on a proposal.

        Args:
            proposal_id: The proposal primary key.
            verdict: The new verdict value.

        Returns:
            The updated :class:`Proposal` instance.

        Raises:
            ValueError: If the proposal does not exist.
        """
        now = datetime.now(UTC)
        stmt = (
            update(Proposal)
            .where(Proposal.id == str(proposal_id))
            .values(verdict=str(verdict), verdict_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()

        updated = await self.get_by_id(proposal_id)
        if updated is None:
            msg = f"Proposal {proposal_id!r} not found"
            raise ValueError(msg)
        return updated
