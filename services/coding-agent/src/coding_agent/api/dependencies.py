"""FastAPI dependency injection for the Coding Agent."""

from __future__ import annotations

from functools import lru_cache

from architect_events.publisher import EventPublisher
from architect_llm.client import LLMClient
from architect_sandbox_client.client import SandboxClient
from coding_agent.agent import CodingAgentLoop
from coding_agent.config import CodingAgentConfig
from coding_agent.models import AgentConfig


@lru_cache(maxsize=1)
def get_config() -> CodingAgentConfig:
    """Return the cached service configuration."""
    return CodingAgentConfig()


_llm_client: LLMClient | None = None
_sandbox_client: SandboxClient | None = None
_event_publisher: EventPublisher | None = None
_agent_loop: CodingAgentLoop | None = None


async def get_llm_client() -> LLMClient:
    """Return a shared :class:`LLMClient` instance."""
    global _llm_client
    if _llm_client is None:
        config = get_config()
        _llm_client = LLMClient(
            api_key=config.architect.claude.api_key.get_secret_value(),
            default_model=config.default_model_id,
        )
    return _llm_client


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


async def get_agent_loop() -> CodingAgentLoop:
    """Return a shared :class:`CodingAgentLoop` instance."""
    global _agent_loop
    if _agent_loop is None:
        config = get_config()
        llm_client = await get_llm_client()
        sandbox_client = await get_sandbox_client()
        event_publisher = await get_event_publisher()

        agent_config = AgentConfig(
            model_id=config.default_model_id,
            max_context_tokens=config.default_max_context_tokens,
            max_output_tokens=config.default_max_output_tokens,
            temperature=config.default_temperature,
        )

        _agent_loop = CodingAgentLoop(
            llm_client=llm_client,
            sandbox_client=sandbox_client,
            event_publisher=event_publisher,
            config=agent_config,
            max_retries=config.max_retries,
        )
    return _agent_loop


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _llm_client, _sandbox_client, _event_publisher, _agent_loop
    if _event_publisher is not None:
        await _event_publisher.close()
        _event_publisher = None
    if _sandbox_client is not None:
        await _sandbox_client.close()
        _sandbox_client = None
    if _llm_client is not None:
        await _llm_client.close()
        _llm_client = None
    _agent_loop = None
