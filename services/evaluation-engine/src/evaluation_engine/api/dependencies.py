"""FastAPI dependency injection for the Evaluation Engine."""

from __future__ import annotations

from functools import lru_cache

from architect_events.publisher import EventPublisher
from architect_sandbox_client.client import SandboxClient
from evaluation_engine.config import EvaluationEngineConfig
from evaluation_engine.evaluator import Evaluator


@lru_cache(maxsize=1)
def get_config() -> EvaluationEngineConfig:
    """Return the cached service configuration."""
    return EvaluationEngineConfig()


_sandbox_client: SandboxClient | None = None
_event_publisher: EventPublisher | None = None
_evaluator: Evaluator | None = None


async def get_sandbox_client() -> SandboxClient:
    """Return a shared :class:`SandboxClient` instance."""
    global _sandbox_client
    if _sandbox_client is None:
        config = get_config()
        _sandbox_client = SandboxClient(base_url=config.sandbox_base_url)
    return _sandbox_client


async def get_event_publisher() -> EventPublisher:
    """Return a connected :class:`EventPublisher` instance."""
    global _event_publisher
    if _event_publisher is None:
        config = get_config()
        _event_publisher = EventPublisher(redis_url=config.architect.redis.url)
        await _event_publisher.connect()
    return _event_publisher


async def get_evaluator() -> Evaluator:
    """Return a shared :class:`Evaluator` instance."""
    global _evaluator
    if _evaluator is None:
        config = get_config()
        sandbox_client = await get_sandbox_client()
        event_publisher = await get_event_publisher()
        _evaluator = Evaluator(
            sandbox_client=sandbox_client,
            event_publisher=event_publisher,
            fail_fast=config.fail_fast,
        )
    return _evaluator


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _sandbox_client, _event_publisher, _evaluator
    if _event_publisher is not None:
        await _event_publisher.close()
        _event_publisher = None
    if _sandbox_client is not None:
        await _sandbox_client.close()
        _sandbox_client = None
    _evaluator = None
