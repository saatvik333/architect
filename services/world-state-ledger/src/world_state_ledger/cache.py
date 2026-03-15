"""Redis-backed state cache for fast world state reads."""

from __future__ import annotations

import json
import random
from typing import Any, cast

import redis.asyncio as aioredis

from architect_common.logging import get_logger

logger = get_logger(component="world_state_ledger.cache")

_STATE_KEY = "wsl:current_state"
_VERSION_KEY = "wsl:current_version"

# Probabilistic early expiration threshold (seconds) and probability.
_EARLY_EXPIRY_THRESHOLD = 30
_EARLY_EXPIRY_PROBABILITY = 0.2


class StateCache:
    """Thin wrapper around Redis for caching the current world state.

    The cache stores the full serialised world state under a single key
    with a configurable TTL.  Individual field lookups are supported via
    namespaced keys.

    To mitigate thundering-herd cache stampedes the default TTL is 300 s
    and reads that find a remaining TTL below 30 s will probabilistically
    return ``None`` (20 % chance) so that a subset of callers trigger a
    background refresh before the key actually expires.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ── Full state ───────────────────────────────────────────────────

    async def get_current_state(self) -> dict[str, Any] | None:
        """Return the cached world state dict, or ``None`` if absent / expired.

        Implements probabilistic early expiration: when the key's remaining
        TTL drops below ``_EARLY_EXPIRY_THRESHOLD`` seconds, there is a 20 %
        chance this method returns ``None`` to allow a caller to refresh the
        cache before it actually expires — spreading the load across time.
        """
        raw: bytes | None = await self._redis.get(_STATE_KEY)
        if raw is None:
            return None

        # Probabilistic early expiration to avoid thundering herd.
        ttl: int = await self._redis.ttl(_STATE_KEY)
        if 0 < ttl < _EARLY_EXPIRY_THRESHOLD and random.random() < _EARLY_EXPIRY_PROBABILITY:
            logger.debug("probabilistic early expiry triggered", ttl_remaining=ttl)
            return None

        return cast(dict[str, Any], json.loads(raw))

    async def set_current_state(
        self, state: dict[str, Any], version: int, ttl_seconds: int = 300
    ) -> None:
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
