"""Generic async repository base class with CRUD operations."""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from architect_db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT: Base]:
    """Generic async repository providing common CRUD operations.

    Subclasses must set ``model_class`` to the ORM model they manage.

    Example::

        class TaskRepository(BaseRepository[Task]):
            model_class = Task
    """

    model_class: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entity: ModelT) -> ModelT:
        """Add *entity* to the session and flush to obtain server defaults.

        Args:
            entity: A new ORM model instance.

        Returns:
            The same instance after being flushed to the database.
        """
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: str) -> ModelT | None:
        """Return the entity with the given primary key, or ``None``.

        Args:
            entity_id: The primary key value.
        """
        return await self._session.get(self.model_class, entity_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Return a paginated list of all entities.

        Args:
            limit: Maximum number of rows to return.
            offset: Number of rows to skip.
        """
        stmt = select(self.model_class).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, entity: ModelT) -> ModelT:
        """Merge changes to *entity* into the session.

        Args:
            entity: A detached or modified ORM model instance.

        Returns:
            The merged instance.
        """
        merged = await self._session.merge(entity)
        await self._session.flush()
        return merged

    async def delete(self, entity: ModelT) -> None:
        """Remove *entity* from the database.

        Args:
            entity: The ORM model instance to delete.
        """
        await self._session.delete(entity)
        await self._session.flush()
