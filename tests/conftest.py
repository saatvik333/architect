"""Shared test fixtures for ARCHITECT integration and E2E tests."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """PostgreSQL connection DSN from environment or default."""
    host = os.environ.get("ARCHITECT_PG_HOST", "localhost")
    port = os.environ.get("ARCHITECT_PG_PORT", "5432")
    user = os.environ.get("ARCHITECT_PG_USER", "architect")
    password = os.environ.get("ARCHITECT_PG_PASSWORD", "architect_dev")
    db = os.environ.get("ARCHITECT_PG_DB", "architect")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Redis connection URL from environment or default."""
    host = os.environ.get("ARCHITECT_REDIS_HOST", "localhost")
    port = os.environ.get("ARCHITECT_REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def gateway_url() -> str:
    """API gateway URL from environment or default."""
    return os.environ.get("ARCHITECT_GATEWAY_URL", "http://localhost:8000")


@pytest_asyncio.fixture
async def async_http_client() -> AsyncGenerator:
    """Shared async HTTP client for integration tests."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client
