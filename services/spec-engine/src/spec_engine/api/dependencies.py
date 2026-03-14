"""FastAPI dependency injection for the Spec Engine."""

from __future__ import annotations

from functools import lru_cache

from architect_llm.client import LLMClient
from spec_engine.config import SpecEngineConfig
from spec_engine.parser import SpecParser


@lru_cache(maxsize=1)
def get_config() -> SpecEngineConfig:
    """Return the cached service configuration."""
    return SpecEngineConfig()


_llm_client: LLMClient | None = None
_spec_parser: SpecParser | None = None


async def get_llm_client() -> LLMClient:
    """Return a shared :class:`LLMClient` instance."""
    global _llm_client
    if _llm_client is None:
        config = get_config()
        _llm_client = LLMClient(
            api_key=config.architect.claude.api_key.get_secret_value(),
            default_model=config.architect.claude.model_id,
        )
    return _llm_client


async def get_spec_parser() -> SpecParser:
    """Return a shared :class:`SpecParser` instance."""
    global _spec_parser
    if _spec_parser is None:
        llm_client = await get_llm_client()
        _spec_parser = SpecParser(llm_client)
    return _spec_parser


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    global _llm_client, _spec_parser
    if _llm_client is not None:
        await _llm_client.close()
        _llm_client = None
    _spec_parser = None
