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
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_recycle: int = 1800,
    pool_timeout: int = 30,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine backed by asyncpg.

    Pool sizing: each service opens at most ``pool_size + max_overflow``
    connections (5 + 5 = 10).  With 14 services this gives a cluster-wide
    maximum of 140.  Ensure Postgres ``max_connections`` is set to at least
    150 (default is 100 -- increase in production).

    Args:
        dsn: PostgreSQL connection string (``postgresql+asyncpg://...``).
        pool_size: Core number of persistent connections in the pool.
        max_overflow: Extra connections allowed above *pool_size* under
            burst load.  These are closed when no longer needed.
        pool_recycle: Seconds after which a connection is recycled (prevents
            stale connections from long-lived pools).
        pool_timeout: Seconds to wait for a connection from the pool before
            raising a timeout error.

    Returns:
        Configured :class:`AsyncEngine` instance.
    """
    return create_async_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle,
        pool_timeout=pool_timeout,
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
