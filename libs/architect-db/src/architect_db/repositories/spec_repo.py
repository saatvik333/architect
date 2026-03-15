"""Specification repository with domain-specific query methods."""

from __future__ import annotations

from sqlalchemy import select

from architect_db.models.spec import Specification
from architect_db.repositories.base import BaseRepository


class SpecificationRepository(BaseRepository[Specification]):
    """Async repository for :class:`Specification` entities."""

    model_class = Specification

    async def get_by_status(self, status: str, *, limit: int = 100) -> list[Specification]:
        """Return specifications filtered by status.

        Args:
            status: The status to filter by.
            limit: Maximum number of rows to return.

        Returns:
            A list of :class:`Specification` rows.
        """
        stmt = (
            select(Specification)
            .where(Specification.status == status)
            .order_by(Specification.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
