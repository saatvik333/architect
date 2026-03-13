"""Redis-backed state cache for fast world state reads."""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from architect_common.logging import get_logger

logger = get_logger(component="world_state_ledger.cache")

_STATE_KEY = "wsl:current_state"
_VERSION_KEY = "wsl:current_version"


class StateCache:
    """Thin wrapper around Redis for caching the current world state.

    The cache stores the full serialised world state under a single key
    with a configurable TTL.  Individual field lookups are supported via
    namespaced keys.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ── Full state ───────────────────────────────────────────────────

    async def get_current_state(self) -> dict | None:
        """Return the cached world state dict, or ``None`` if absent / expired."""
        raw: bytes | None = await self._redis.get(_STATE_KEY)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_current_state(self, state: dict, version: int, ttl_seconds: int = 30) -> None:
        """Write *state* to the cache with *ttl_seconds* expiry."""
        payload = json.dumps(state, default=str)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(_STATE_KEY, payload, ex=ttl_seconds)
            pipe.set(_VERSION_KEY, str(version), ex=ttl_seconds)
            await pipe.execute()
        logger.debug("state cached", version=version, ttl=ttl_seconds)

    async def invalidate(self) -> None:
        """Remove the cached state (e.g. after a non-standard mutation)."""
        await self._redis.delete(_STATE_KEY, _VERSION_KEY)
        logger.debug("cache invalidated")

    # ── Individual field access ──────────────────────────────────────

    async def get_field(self, path: str) -> str | None:
        """Read a single cached field by dot-path key."""
        key = f"wsl:field:{path}"
        raw: bytes | None = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode()

    async def set_field(self, path: str, value: str, ttl_seconds: int = 30) -> None:
        """Cache a single field value with TTL."""
        key = f"wsl:field:{path}"
        await self._redis.set(key, value, ex=ttl_seconds)
