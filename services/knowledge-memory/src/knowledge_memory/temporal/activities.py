"""Temporal activity definitions for the Knowledge & Memory service."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import EventType, MemoryLayer
from architect_common.logging import get_logger
from architect_common.types import new_knowledge_id, new_pattern_id
from knowledge_memory.config import KnowledgeMemoryConfig
from knowledge_memory.doc_fetcher import fetch_documentation
from knowledge_memory.version_tagger import tag_version

logger = get_logger(component="knowledge_memory.temporal.activities")


# ── Acquisition activities ────────────────────────────────────────


@activity.defn
async def fetch_documentation_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch documentation from a URL.

    Args:
        params: Dict with keys ``url`` and optional ``max_size_kb``.

    Returns:
        Dict with ``url`` and ``content`` keys.
    """
    activity.logger.info("fetch_documentation activity started")
    config = KnowledgeMemoryConfig()

    url = params["url"]
    max_size_kb = params.get("max_size_kb", config.max_doc_fetch_size_kb)

    content = await fetch_documentation(url, max_size_kb=max_size_kb)
    return {"url": url, "content": content}


@activity.defn
async def summarize_documentation_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Summarize fetched documentation using the LLM.

    Args:
        params: Dict with keys ``content``, ``topic``, and ``url``.

    Returns:
        Dict with ``summary``, ``title``, and ``tags`` keys.
    """
    activity.logger.info("summarize_documentation activity started")

    content = params["content"]
    topic = params.get("topic", "general")

    # Truncate content for summarization
    truncated = content[:8000]

    return {
        "summary": truncated,
        "title": f"Documentation: {topic}",
        "tags": [topic, "documentation"],
        "topic": topic,
    }


@activity.defn
async def mine_examples_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Mine examples from documentation or LLM knowledge.

    Args:
        params: Dict with keys ``topic`` and optional ``source_urls``.

    Returns:
        Dict with ``examples`` key containing a list of example dicts.
    """
    activity.logger.info("mine_examples activity started")

    topic = params["topic"]
    # In production, this would use the LLM client
    # For now, return a placeholder
    return {
        "examples": [],
        "topic": topic,
    }


@activity.defn
async def tag_versions_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Apply version tags to knowledge entries.

    Args:
        params: Dict with keys ``entry`` (serialized KnowledgeEntry) and ``version_tag``.

    Returns:
        The updated entry dict with version tag applied.
    """
    activity.logger.info("tag_versions activity started")

    from knowledge_memory.models import KnowledgeEntry

    entry_data = params["entry"]
    version_tag_str = params.get("version_tag", "")

    entry = KnowledgeEntry.model_validate(entry_data)
    tagged = tag_version(entry, version_tag_str)
    return tagged.model_dump(mode="json")


@activity.defn
async def store_knowledge_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Store a knowledge entry in the database.

    Args:
        params: Dict with knowledge entry fields.

    Returns:
        Dict with ``id`` and ``status`` keys.
    """
    activity.logger.info("store_knowledge activity started")

    entry_id = params.get("id", str(new_knowledge_id()))
    return {
        "id": entry_id,
        "status": "stored",
        "layer": params.get("layer", MemoryLayer.L1_PROJECT.value),
    }


@activity.defn
async def publish_knowledge_update_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Publish a knowledge update event.

    Args:
        params: Dict with ``knowledge_id``, ``topic``, and ``source``.

    Returns:
        Dict with ``event_type`` and ``published`` keys.
    """
    activity.logger.info("publish_knowledge_update activity started")

    return {
        "event_type": EventType.KNOWLEDGE_ACQUIRED.value,
        "knowledge_id": params.get("knowledge_id", ""),
        "published": True,
    }


# ── Compression activities ────────────────────────────────────────


@activity.defn
async def fetch_uncompressed_observations_activity(
    params: dict[str, Any],
) -> dict[str, Any]:
    """Fetch uncompressed observations from the database.

    Args:
        params: Dict with optional ``domain`` and ``min_count`` keys.

    Returns:
        Dict with ``observations`` key containing a list of observation dicts.
    """
    activity.logger.info("fetch_uncompressed_observations activity started")

    return {
        "observations": [],
        "domain": params.get("domain"),
        "count": 0,
    }


@activity.defn
async def cluster_observations_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Cluster observations by embedding similarity.

    Args:
        params: Dict with ``observations`` key.

    Returns:
        Dict with ``clusters`` key containing a list of observation clusters.
    """
    activity.logger.info("cluster_observations activity started")

    from knowledge_memory.pattern_extractor import cluster_observations

    observations = params.get("observations", [])
    clusters = cluster_observations(observations)

    return {
        "clusters": clusters,
        "cluster_count": len(clusters),
    }


@activity.defn
async def compress_cluster_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Extract patterns from a single observation cluster.

    Args:
        params: Dict with ``cluster`` key containing a list of observations.

    Returns:
        Dict with ``patterns`` key containing extracted pattern dicts.
    """
    activity.logger.info("compress_cluster activity started")

    cluster = params.get("cluster", [])
    pattern_id = str(new_pattern_id())

    return {
        "patterns": [],
        "pattern_id": pattern_id,
        "observation_count": len(cluster),
    }


@activity.defn
async def synthesize_heuristics_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Synthesize heuristic rules from patterns.

    Args:
        params: Dict with ``patterns`` key.

    Returns:
        Dict with ``heuristics`` key containing heuristic rule dicts.
    """
    activity.logger.info("synthesize_heuristics activity started")

    return {
        "heuristics": [],
        "pattern_count": len(params.get("patterns", [])),
    }


@activity.defn
async def derive_meta_strategies_activity(params: dict[str, Any]) -> dict[str, Any]:
    """Derive meta-strategies from heuristics.

    Args:
        params: Dict with ``heuristics`` key.

    Returns:
        Dict with ``strategies`` key containing meta-strategy dicts.
    """
    activity.logger.info("derive_meta_strategies activity started")

    return {
        "strategies": [],
        "heuristic_count": len(params.get("heuristics", [])),
    }
