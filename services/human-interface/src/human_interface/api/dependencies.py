"""FastAPI dependency injection for the Human Interface."""

from __future__ import annotations

from functools import lru_cache

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from human_interface.config import HumanInterfaceConfig
from human_interface.ws_manager import WebSocketManager


@lru_cache(maxsize=1)
def get_config() -> HumanInterfaceConfig:
    """Return the cached service configuration."""
    return HumanInterfaceConfig()


# ── WebSocket manager ─────────────────────────────────────────────

_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Return the shared :class:`WebSocketManager` instance."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


def set_ws_manager(manager: WebSocketManager) -> None:
    """Override the shared WebSocket manager (used during service startup)."""
    global _ws_manager
    _ws_manager = manager


# ── HTTP client ───────────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared :class:`httpx.AsyncClient` instance.

    Raises:
        RuntimeError: If :func:`set_http_client` has not been called.
    """
    if _http_client is None:
        msg = "HTTP client not initialised. Call set_http_client() during startup."
        raise RuntimeError(msg)
    return _http_client


def set_http_client(client: httpx.AsyncClient) -> None:
    """Override the shared HTTP client (used during service startup)."""
    global _http_client
    _http_client = client


# ── Database engine / session factory ────────────────────────────

_db_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_db_engine() -> AsyncEngine:
    """Return the shared async database engine."""
    if _db_engine is None:
        msg = "Database engine not initialised. Call set_db_engine() during startup."
        raise RuntimeError(msg)
    return _db_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory."""
    if _session_factory is None:
        msg = "Session factory not initialised. Call set_db_engine() during startup."
        raise RuntimeError(msg)
    return _session_factory


def set_db_engine(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> None:
    """Set the shared database engine and session factory (called during startup)."""
    global _db_engine, _session_factory
    _db_engine = engine
    _session_factory = factory


# ── Cleanup ───────────────────────────────────────────────────────


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _ws_manager, _http_client, _db_engine, _session_factory
    if _http_client is not None:
        await _http_client.aclose()
    if _db_engine is not None:
        await _db_engine.dispose()
    _ws_manager = None
    _http_client = None
    _db_engine = None
    _session_factory = None
