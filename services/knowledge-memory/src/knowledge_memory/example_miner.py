"""LLM-powered example mining from documentation and source material.

Analyzes documentation content and extracts concrete code examples
or usage patterns relevant to a given topic.
"""

from __future__ import annotations

import json

import httpx

from architect_common.enums import ContentType, MemoryLayer
from architect_common.logging import get_logger
from architect_common.types import new_knowledge_id
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from knowledge_memory.doc_fetcher import fetch_documentation
from knowledge_memory.models import KnowledgeEntry

logger = get_logger(component="knowledge_memory.example_miner")


async def mine_examples(
    topic: str,
    llm_client: LLMClient,
    *,
    source_urls: list[str] | None = None,
    max_doc_size_kb: int = 500,
) -> list[KnowledgeEntry]:
    """Mine code examples and usage patterns for a given topic.

    If *source_urls* are provided, fetches each document and asks the LLM
    to extract relevant examples.  Otherwise, asks the LLM to generate
    examples from its training knowledge.

    Args:
        topic: The topic to mine examples for.
        llm_client: LLM client for analysis.
        source_urls: Optional list of documentation URLs to mine from.
        max_doc_size_kb: Maximum size for each fetched document.

    Returns:
        List of :class:`KnowledgeEntry` objects containing extracted examples.
    """
    source_content = ""

    if source_urls:
        # Reuse a single HTTP client across all URL fetches to avoid
        # creating/destroying a connection pool per URL.
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http_client:
            for url in source_urls:
                try:
                    doc_text = await fetch_documentation(
                        url, max_size_kb=max_doc_size_kb, client=http_client
                    )
                    source_content += f"\n\n--- Source: {url} ---\n{doc_text[:5000]}"
                except Exception:
                    logger.warning("failed to fetch source URL", url=url)
                    continue

    if source_content:
        prompt_content = (
            f"Topic: {topic}\n\n"
            f"Source documentation:\n{source_content}\n\n"
            "Extract concrete code examples and usage patterns from the documentation above. "
            "Return a JSON array of example objects with keys: "
            '"title", "content" (the example code/text), "tags" (string array).'
        )
    else:
        prompt_content = (
            f"Topic: {topic}\n\n"
            "Provide concrete code examples and usage patterns for this topic. "
            "Return a JSON array of example objects with keys: "
            '"title", "content" (the example code/text), "tags" (string array).'
        )

    request = LLMRequest(
        system_prompt=(
            "You are an expert software engineering instructor. "
            "You extract or generate high-quality, runnable code examples. "
            "Always return a JSON array of example objects."
        ),
        messages=[{"role": "user", "content": prompt_content}],
        max_tokens=4000,
        temperature=0.3,
    )

    response = await llm_client.generate(request)

    examples: list[KnowledgeEntry] = []
    try:
        raw_examples = json.loads(response.content)
        if not isinstance(raw_examples, list):
            raw_examples = [raw_examples]

        for re_ in raw_examples:
            entry = KnowledgeEntry(
                id=new_knowledge_id(),
                layer=MemoryLayer.L1_PROJECT,
                topic=topic,
                title=re_.get("title", f"Example: {topic}"),
                content=re_.get("content", ""),
                content_type=ContentType.EXAMPLE,
                tags=re_.get("tags", [topic]),
                source="example_mine",
            )
            examples.append(entry)
    except (json.JSONDecodeError, TypeError):
        logger.warning("failed to parse LLM example response, using raw content")
        examples.append(
            KnowledgeEntry(
                id=new_knowledge_id(),
                layer=MemoryLayer.L1_PROJECT,
                topic=topic,
                title=f"Example: {topic}",
                content=response.content,
                content_type=ContentType.EXAMPLE,
                tags=[topic],
                source="example_mine:parse_fallback",
            )
        )

    logger.info("mined examples", topic=topic, count=len(examples))
    return examples
