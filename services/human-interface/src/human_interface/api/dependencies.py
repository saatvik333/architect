"""FastAPI dependency injection for the Human Interface."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from architect_common.dependencies import ServiceDependency
from human_interface.config import HumanInterfaceConfig
from human_interface.ws_manager import WebSocketManager


@lru_cache(maxsize=1)
def get_config() -> HumanInterfaceConfig:
    """Return the cached service configuration."""
    return HumanInterfaceConfig()


# ── WebSocket manager ─────────────────────────────────────────────

_ws_manager = ServiceDependency[WebSocketManager]("WebSocketManager")

get_ws_manager = _ws_manager.get
set_ws_manager = _ws_manager.set

# ── HTTP client ───────────────────────────────────────────────────

_http_client = ServiceDependency[httpx.AsyncClient]("HTTP client")

get_http_client = _http_client.get
set_http_client = _http_client.set

# ── Database engine / session factory ────────────────────────────

_db_engine = ServiceDependency[AsyncEngine]("Database engine")
_session_factory = ServiceDependency[async_sessionmaker[AsyncSession]]("Session factory")

get_db_engine = _db_engine.get
get_session_factory = _session_factory.get


def set_db_engine(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> None:
    """Set the shared database engine and session factory (called during startup)."""
    _db_engine.set(engine)
    _session_factory.set(factory)


# ── Temporal client ────────────────────────────────────────────────

# Temporal client uses Any to avoid a heavy import; callers know the concrete type.
_temporal_client: ServiceDependency[Any] = ServiceDependency("Temporal client")

get_temporal_client = _temporal_client.get
set_temporal_client = _temporal_client.set

# ── Cleanup ───────────────────────────────────────────────────────


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _http_client.cleanup()  # calls aclose()
    # AsyncEngine uses dispose(), not aclose() — handle manually
    engine = _db_engine._instance
    if engine is not None:
        await engine.dispose()
    _db_engine._instance = None
    _session_factory._instance = None
    _ws_manager._instance = None
    _temporal_client._instance = None
