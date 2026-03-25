"""LLM-powered pattern extraction from clusters of observations.

Groups similar observations using cosine similarity and then uses the
LLM to distill reusable patterns from each cluster.
"""

from __future__ import annotations

import json
from typing import Any

from architect_common.enums import ContentType, MemoryLayer
from architect_common.logging import get_logger
from architect_common.types import new_knowledge_id, new_pattern_id
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from knowledge_memory.models import KnowledgeEntry
from knowledge_memory.similarity import cosine_similarity

logger = get_logger(component="knowledge_memory.pattern_extractor")


def cluster_observations(
    observations: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.7,
) -> list[list[dict[str, Any]]]:
    """Group observations into clusters based on embedding similarity.

    Uses a simple greedy clustering approach: for each observation,
    find the first cluster whose centroid is within the similarity threshold.
    If none, start a new cluster.
    """
    clusters: list[list[dict[str, Any]]] = []
    centroids: list[list[float]] = []

    for obs in observations:
        emb = obs.get("embedding") or []
        if isinstance(emb, str):
            emb = json.loads(emb)

        if not emb:
            # Observations without embeddings go into their own cluster
            clusters.append([obs])
            centroids.append([])
            continue

        placed = False
        for i, centroid in enumerate(centroids):
            if centroid and cosine_similarity(emb, centroid) >= similarity_threshold:
                clusters[i].append(obs)
                # Update centroid as running average
                centroids[i] = [
                    (c * len(clusters[i]) + e) / (len(clusters[i]) + 1)
                    for c, e in zip(centroid, emb, strict=False)
                ]
                placed = True
                break

        if not placed:
            clusters.append([obs])
            centroids.append(list(emb))

    return clusters


async def extract_patterns(
    observations: list[dict[str, Any]],
    llm_client: LLMClient,
) -> list[KnowledgeEntry]:
    """Use an LLM to extract reusable patterns from a cluster of observations.

    Each cluster of observations is summarized into one or more patterns
    that can be stored in L2 (pattern layer) of the knowledge hierarchy.
    """
    if not observations:
        return []

    # Build a summary of observations for the LLM
    obs_summaries = []
    for obs in observations:
        obs_summaries.append(
            f"- [{obs.get('observation_type', 'unknown')}] {obs.get('description', '')}"
            f" (domain: {obs.get('domain', 'general')}, outcome: {obs.get('outcome', 'N/A')})"
        )

    obs_text = "\n".join(obs_summaries)
    domain = observations[0].get("domain", "general") if observations else "general"

    request = LLMRequest(
        system_prompt=(
            "You are an expert software engineering pattern analyst. "
            "Given a set of observations from task execution, extract reusable patterns. "
            "Return a JSON array of pattern objects with keys: "
            '"title", "content", "confidence" (0-1 float), "tags" (string array).'
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Domain: {domain}\n\n"
                    f"Observations ({len(observations)} total):\n{obs_text}\n\n"
                    "Extract reusable patterns from these observations. "
                    "Return ONLY a JSON array."
                ),
            }
        ],
        max_tokens=4000,
        temperature=0.3,
    )

    response = await llm_client.generate(request)

    # Parse the LLM response
    patterns: list[KnowledgeEntry] = []
    try:
        raw_patterns = json.loads(response.content)
        if not isinstance(raw_patterns, list):
            raw_patterns = [raw_patterns]

        for rp in raw_patterns:
            pattern_id = new_pattern_id()
            entry = KnowledgeEntry(
                id=new_knowledge_id(),
                layer=MemoryLayer.L2_PATTERN,
                topic=domain,
                title=rp.get("title", "Extracted pattern"),
                content=rp.get("content", response.content),
                content_type=ContentType.PATTERN,
                confidence=float(rp.get("confidence", 0.5)),
                tags=rp.get("tags", []),
                source=f"pattern_extraction:{pattern_id}",
            )
            patterns.append(entry)
    except (json.JSONDecodeError, TypeError):
        logger.warning("failed to parse LLM pattern response, using raw content")
        patterns.append(
            KnowledgeEntry(
                id=new_knowledge_id(),
                layer=MemoryLayer.L2_PATTERN,
                topic=domain,
                title="Extracted pattern",
                content=response.content,
                content_type=ContentType.PATTERN,
                confidence=0.3,
                source="pattern_extraction:parse_fallback",
            )
        )

    logger.info("extracted patterns", count=len(patterns), domain=domain)
    return patterns
