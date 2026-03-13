"""Unit tests for the StateCache."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from world_state_ledger.cache import StateCache
from world_state_ledger.models import WorldState


class TestGetCurrentState:
    """Tests for StateCache.get_current_state."""

    async def test_returns_none_on_cache_miss(self, state_cache: StateCache) -> None:
        state_cache._redis.get = AsyncMock(return_value=None)
        result = await state_cache.get_current_state()
        assert result is None

    async def test_returns_dict_on_cache_hit(self, state_cache: StateCache) -> None:
        state = WorldState(version=5)
        raw = json.dumps(state.model_dump(mode="json"), default=str).encode()
        state_cache._redis.get = AsyncMock(return_value=raw)

        result = await state_cache.get_current_state()
        assert result is not None
        assert result["version"] == 5


class TestSetCurrentState:
    """Tests for StateCache.set_current_state."""

    async def test_writes_to_redis_pipeline(self, state_cache: StateCache) -> None:
        state = WorldState(version=3)
        data = state.model_dump(mode="json")

        pipe = state_cache._redis.pipeline.return_value
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=False)
        pipe.set = MagicMock()
        pipe.execute = AsyncMock()

        await state_cache.set_current_state(data, version=3, ttl_seconds=60)

        # Pipeline should have been entered and executed.
        pipe.execute.assert_awaited_once()


class TestInvalidate:
    """Tests for StateCache.invalidate."""

    async def test_deletes_keys(self, state_cache: StateCache) -> None:
        state_cache._redis.delete = AsyncMock()
        await state_cache.invalidate()
        state_cache._redis.delete.assert_awaited_once()


class TestFieldAccess:
    """Tests for get_field / set_field."""

    async def test_get_field_returns_none_on_miss(self, state_cache: StateCache) -> None:
        state_cache._redis.get = AsyncMock(return_value=None)
        result = await state_cache.get_field("budget.remaining_tokens")
        assert result is None

    async def test_get_field_returns_value(self, state_cache: StateCache) -> None:
        state_cache._redis.get = AsyncMock(return_value=b"8000")
        result = await state_cache.get_field("budget.remaining_tokens")
        assert result == "8000"

    async def test_set_field_writes_with_ttl(self, state_cache: StateCache) -> None:
        state_cache._redis.set = AsyncMock()
        await state_cache.set_field("budget.remaining_tokens", "8000", ttl_seconds=15)
        state_cache._redis.set.assert_awaited_once_with(
            "wsl:field:budget.remaining_tokens", "8000", ex=15
        )
