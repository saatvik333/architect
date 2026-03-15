"""Tests for TokenBucketRateLimiter — capacity, exhaustion, refill, and concurrency."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from architect_llm.rate_limiter import TokenBucketRateLimiter

# ── Token bucket allows requests under limit ────────────────────────


class TestTokenBucketAllowsUnderLimit:
    async def test_acquire_single_request(self) -> None:
        """A fresh limiter should allow a single request immediately."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=1000,
            max_requests_per_minute=10,
        )
        # Should return immediately without blocking
        await asyncio.wait_for(limiter.acquire(estimated_tokens=100), timeout=1.0)

    async def test_acquire_multiple_requests_under_limit(self) -> None:
        """Multiple requests under the limit should all succeed immediately."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=10_000,
            max_requests_per_minute=100,
        )
        for _ in range(10):
            await asyncio.wait_for(limiter.acquire(estimated_tokens=100), timeout=1.0)

    async def test_acquire_with_default_tokens(self) -> None:
        """acquire() with default estimated_tokens=1 should work."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100,
            max_requests_per_minute=10,
        )
        await asyncio.wait_for(limiter.acquire(), timeout=1.0)

    async def test_acquire_exact_capacity(self) -> None:
        """Consuming exactly the full token capacity should succeed."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=1000,
            max_requests_per_minute=10,
        )
        await asyncio.wait_for(limiter.acquire(estimated_tokens=1000), timeout=1.0)

    async def test_acquire_exact_request_capacity(self) -> None:
        """Consuming all available requests should succeed."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100_000,
            max_requests_per_minute=5,
        )
        for _ in range(5):
            await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=1.0)


# ── Token bucket rejects when exhausted ─────────────────────────────


class TestTokenBucketRejectsWhenExhausted:
    async def test_blocks_when_tokens_exhausted(self) -> None:
        """After consuming all tokens, acquire should block (not return immediately)."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100,
            max_requests_per_minute=1000,
        )
        # Consume all tokens
        await limiter.acquire(estimated_tokens=100)

        # Next acquire should block (timeout quickly to avoid hanging)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=0.1)

    async def test_blocks_when_requests_exhausted(self) -> None:
        """After consuming all request slots, acquire should block."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100_000,
            max_requests_per_minute=2,
        )
        # Consume all request slots
        await limiter.acquire(estimated_tokens=1)
        await limiter.acquire(estimated_tokens=1)

        # Next acquire should block
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=0.1)

    async def test_blocks_when_both_exhausted(self) -> None:
        """When both buckets are empty, acquire should block."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=50,
            max_requests_per_minute=2,
        )
        await limiter.acquire(estimated_tokens=25)
        await limiter.acquire(estimated_tokens=25)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=0.1)


# ── Token bucket refills over time ──────────────────────────────────


class TestTokenBucketRefill:
    async def test_tokens_refill_after_time_passes(self) -> None:
        """Tokens should refill proportionally to elapsed time."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=6000,  # 100 tokens/sec
            max_requests_per_minute=6000,  # won't be the bottleneck
        )
        # Consume all tokens
        await limiter.acquire(estimated_tokens=6000)

        # Manually advance the refill clock by simulating time passage.
        # The refill rate is 6000 tokens/minute = 100 tokens/second.
        # After 0.5 seconds, ~50 tokens should be available.
        original_monotonic = time.monotonic

        # Shift time forward by 1 second (= 100 tokens refilled)
        with patch("time.monotonic", side_effect=lambda: original_monotonic() + 1.0):
            # Should be able to acquire ~100 tokens now
            await asyncio.wait_for(limiter.acquire(estimated_tokens=50), timeout=0.5)

    async def test_refill_does_not_exceed_max(self) -> None:
        """Refill should cap at max_tokens_per_minute."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100,
            max_requests_per_minute=100,
        )
        # Don't consume anything — bucket starts full
        # Internal state: _available_tokens should be 100.0

        # Simulate a lot of time passing
        original_last_refill = limiter._last_refill
        limiter._last_refill = original_last_refill - 600  # 10 minutes ago

        limiter._refill()

        # Should be capped at max
        assert limiter._available_tokens == float(100)
        assert limiter._available_requests == float(100)

    def test_refill_proportional_to_elapsed(self) -> None:
        """_refill() should add tokens proportional to elapsed time."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=6000,
            max_requests_per_minute=60,
        )
        # Drain tokens partially
        limiter._available_tokens = 0.0
        limiter._available_requests = 0.0

        # Simulate 0.5 minutes elapsed
        limiter._last_refill = time.monotonic() - 30  # 30 seconds = 0.5 minutes

        limiter._refill()

        # Should have refilled ~3000 tokens and ~30 requests
        assert limiter._available_tokens == pytest.approx(3000, abs=100)
        assert limiter._available_requests == pytest.approx(30, abs=2)

    def test_refill_with_no_time_elapsed(self) -> None:
        """Refilling immediately should add nothing."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=1000,
            max_requests_per_minute=60,
        )
        # Drain to zero
        limiter._available_tokens = 0.0
        limiter._available_requests = 0.0
        limiter._last_refill = time.monotonic()

        limiter._refill()

        # Should be very close to zero (just microseconds of refill)
        assert limiter._available_tokens < 1.0
        assert limiter._available_requests < 1.0


# ── Concurrent access safety ────────────────────────────────────────


class TestConcurrentAccess:
    async def test_concurrent_acquires_do_not_over_consume(self) -> None:
        """Multiple concurrent acquire() calls should not consume
        more tokens than available.
        """
        max_requests = 10
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=100_000,  # Tokens won't be the bottleneck
            max_requests_per_minute=max_requests,
        )

        # Launch more concurrent tasks than available request slots
        results: list[bool] = []

        async def try_acquire() -> bool:
            try:
                await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=0.15)
                return True
            except TimeoutError:
                return False

        tasks = [asyncio.create_task(try_acquire()) for _ in range(max_requests + 5)]
        results = await asyncio.gather(*tasks)

        # Exactly max_requests should have succeeded
        succeeded = sum(1 for r in results if r)
        assert succeeded == max_requests

    async def test_concurrent_token_consumption_is_safe(self) -> None:
        """Concurrent tasks consuming tokens should respect the total budget."""
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=500,
            max_requests_per_minute=1000,  # Requests won't be the bottleneck
        )

        results: list[bool] = []

        async def try_acquire() -> bool:
            try:
                await asyncio.wait_for(limiter.acquire(estimated_tokens=100), timeout=0.15)
                return True
            except TimeoutError:
                return False

        # 500 tokens available, each consuming 100 => 5 should succeed
        tasks = [asyncio.create_task(try_acquire()) for _ in range(8)]
        results = await asyncio.gather(*tasks)

        succeeded = sum(1 for r in results if r)
        assert succeeded == 5

    async def test_lock_prevents_race_conditions(self) -> None:
        """The internal lock should prevent two tasks from reading the
        same available count and both deciding they can proceed.
        """
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=1,
            max_requests_per_minute=1,
        )

        results: list[bool] = []

        async def try_acquire() -> bool:
            try:
                await asyncio.wait_for(limiter.acquire(estimated_tokens=1), timeout=0.15)
                return True
            except TimeoutError:
                return False

        # Only 1 slot available — exactly 1 should succeed
        tasks = [asyncio.create_task(try_acquire()) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert sum(1 for r in results if r) == 1


# ── Initialization ──────────────────────────────────────────────────


class TestInitialization:
    def test_default_values(self) -> None:
        limiter = TokenBucketRateLimiter()
        assert limiter._max_tokens == 100_000
        assert limiter._max_requests == 60
        assert limiter._available_tokens == 100_000.0
        assert limiter._available_requests == 60.0

    def test_custom_values(self) -> None:
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=50_000,
            max_requests_per_minute=30,
        )
        assert limiter._max_tokens == 50_000
        assert limiter._max_requests == 30
        assert limiter._available_tokens == 50_000.0
        assert limiter._available_requests == 30.0

    def test_lock_is_created(self) -> None:
        limiter = TokenBucketRateLimiter()
        assert isinstance(limiter._lock, asyncio.Lock)


# ── Wait time calculation ───────────────────────────────────────────


class TestWaitTimeCalculation:
    async def test_wait_time_is_proportional_to_deficit(self) -> None:
        """The sleep time should be roughly proportional to how many
        tokens are missing.
        """
        limiter = TokenBucketRateLimiter(
            max_tokens_per_minute=60,  # 1 token/sec
            max_requests_per_minute=1000,
        )
        # Consume all tokens
        await limiter.acquire(estimated_tokens=60)

        # Now requesting 1 token — should need to wait ~1 second
        # We verify this by patching asyncio.sleep and checking the arg
        sleep_durations: list[float] = []
        original_sleep = asyncio.sleep

        async def recording_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            # Actually sleep a tiny bit to advance time
            await original_sleep(0.001)
            # Force-refill to let the acquire succeed
            limiter._available_tokens = 10.0
            limiter._available_requests = 10.0

        with patch("asyncio.sleep", side_effect=recording_sleep):
            await limiter.acquire(estimated_tokens=1)

        assert len(sleep_durations) >= 1
        # The wait should be roughly 1 second (1 token deficit / 60 tokens per minute * 60 sec)
        assert sleep_durations[0] >= 0.5
