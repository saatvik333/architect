"""LLM-powered example mining from documentation and source material.

Analyzes documentation content and extracts concrete code examples
or usage patterns relevant to a given topic.
"""

from __future__ import annotations

import httpx

from architect_common.enums import ContentType, MemoryLayer
from architect_common.logging import get_logger
from architect_common.types import new_knowledge_id
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from knowledge_memory.doc_fetcher import fetch_documentation
from knowledge_memory.llm_utils import parse_llm_json_array
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
        for url in source_urls:
            try:
                doc_text = await fetch_documentation(url, max_size_kb=max_doc_size_kb)
                source_content += f"\n\n--- Source: {url} ---\n{doc_text[:5000]}"
            except (httpx.HTTPError, ValueError, ConnectionError) as exc:
                logger.warning("failed_to_fetch_source_url", url=url, error=str(exc))
                continue

    if source_content:
        prompt_content = (
            f"Topic: <user_input>{topic}</user_input>\n\n"
            f"Source documentation:\n<user_input>{source_content}</user_input>\n\n"
            "Extract concrete code examples and usage patterns from the documentation above. "
            "Return a JSON array of example objects with keys: "
            '"title", "content" (the example code/text), "tags" (string array).'
        )
    else:
        prompt_content = (
            f"Topic: <user_input>{topic}</user_input>\n\n"
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
    raw_examples = parse_llm_json_array(response.content, logger)

    if not raw_examples:
        # Fallback: preserve the raw LLM content as a single entry
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
    else:
        for raw_example in raw_examples:
            entry = KnowledgeEntry(
                id=new_knowledge_id(),
                layer=MemoryLayer.L1_PROJECT,
                topic=topic,
                title=raw_example.get("title", f"Example: {topic}"),
                content=raw_example.get("content", ""),
                content_type=ContentType.EXAMPLE,
                tags=raw_example.get("tags", [topic]),
                source="example_mine",
            )
            examples.append(entry)

    logger.info("mined examples", topic=topic, count=len(examples))
    return examples
