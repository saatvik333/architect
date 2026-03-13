"""Session context manager for transactional database access."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional :class:`AsyncSession`, committing on success.

    On unhandled exceptions the session is rolled back automatically by the
    context manager.  Callers should use this as an async generator::

        async for session in get_session(factory):
            ...

    Or more idiomatically via dependency injection.

    Args:
        factory: The session factory created by :func:`create_session_factory`.

    Yields:
        An :class:`AsyncSession` bound to a transaction.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
