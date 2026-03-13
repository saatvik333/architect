"""Token-bucket rate limiter for LLM API calls."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Async-friendly dual-bucket rate limiter (tokens + requests per minute).

    Two independent buckets are maintained:

    * **Token bucket** — limits total estimated tokens consumed per minute.
    * **Request bucket** — limits the number of API requests per minute.

    :meth:`acquire` blocks (via ``asyncio.sleep``) until both buckets have
    sufficient capacity.
    """

    def __init__(
        self,
        max_tokens_per_minute: int = 100_000,
        max_requests_per_minute: int = 60,
    ) -> None:
        self._max_tokens = max_tokens_per_minute
        self._max_requests = max_requests_per_minute

        self._available_tokens = float(max_tokens_per_minute)
        self._available_requests = float(max_requests_per_minute)

        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill both buckets proportional to elapsed time."""
        now = time.monotonic()
        elapsed_minutes = (now - self._last_refill) / 60.0
        self._last_refill = now

        self._available_tokens = min(
            float(self._max_tokens),
            self._available_tokens + elapsed_minutes * self._max_tokens,
        )
        self._available_requests = min(
            float(self._max_requests),
            self._available_requests + elapsed_minutes * self._max_requests,
        )

    async def acquire(self, estimated_tokens: int = 1) -> None:
        """Wait until both buckets have enough capacity, then consume.

        Args:
            estimated_tokens: Estimated total tokens (input + output) for the
                upcoming request.  Defaults to 1 (request-only limiting).
        """
        while True:
            async with self._lock:
                self._refill()

                if self._available_tokens >= estimated_tokens and self._available_requests >= 1.0:
                    self._available_tokens -= estimated_tokens
                    self._available_requests -= 1.0
                    return

                # Calculate how long to wait for the most constrained bucket.
                wait_tokens = 0.0
                if self._available_tokens < estimated_tokens:
                    deficit = estimated_tokens - self._available_tokens
                    wait_tokens = (deficit / self._max_tokens) * 60.0

                wait_requests = 0.0
                if self._available_requests < 1.0:
                    deficit = 1.0 - self._available_requests
                    wait_requests = (deficit / self._max_requests) * 60.0

                wait_seconds = max(wait_tokens, wait_requests, 0.01)

            await asyncio.sleep(wait_seconds)
