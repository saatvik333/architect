"""Async SQLAlchemy engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    dsn: str,
    *,
    pool_min: int = 2,
    pool_max: int = 10,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine backed by asyncpg.

    Args:
        dsn: PostgreSQL connection string (``postgresql+asyncpg://...``).
        pool_min: Minimum number of connections in the pool.
        pool_max: Maximum number of connections in the pool.

    Returns:
        Configured :class:`AsyncEngine` instance.
    """
    return create_async_engine(
        dsn,
        pool_size=pool_min,
        max_overflow=pool_max - pool_min,
        pool_pre_ping=True,
        echo=False,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: The :class:`AsyncEngine` to bind sessions to.

    Returns:
        A session factory that produces :class:`AsyncSession` instances.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
