"""FastAPI route definitions for the Knowledge & Memory service."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from architect_common.enums import HealthStatus
from architect_common.health import HealthResponse
from architect_common.logging import get_logger
from architect_common.types import AgentId, HeuristicId, KnowledgeId, TaskId
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.models import (
    AcquireKnowledgeRequest,
    CompressionRequest,
    CompressionResult,
    FeedbackRequest,
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeQueryResult,
    KnowledgeStats,
)
from knowledge_memory.working_memory import WorkingMemoryStore

from .dependencies import get_heuristic_engine, get_knowledge_store, get_working_memory

logger = get_logger(component="knowledge_memory.api.routes")

router = APIRouter()


# ── Request / Response schemas ─────────────────────────────────────


class WorkingMemoryUpdate(BaseModel):
    """Request body for updating working memory."""

    scratchpad_updates: dict[str, object] | None = None
    add_context_entries: list[str] | None = None


class HeuristicMatchRequest(BaseModel):
    """Query parameters for heuristic matching."""

    task_type: str | None = None
    domain: str | None = None


class HeuristicOutcomeRequest(BaseModel):
    """Request body for recording a heuristic outcome."""

    success: bool


# ── Knowledge endpoints ────────────────────────────────────────────


@router.post("/api/v1/knowledge/query", response_model=KnowledgeQueryResult)
async def query_knowledge(
    body: KnowledgeQuery,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeQueryResult:
    """Search knowledge entries by semantic similarity and filters."""
    # NOTE: query_embedding=[] means semantic ranking is NOT applied.
    # The store falls back to metadata-only filtering (layer, topic, content_type).
    # Once the embedding service is integrated, the query text should be encoded
    # here via the embedding model before being passed to store.search().
    query_embedding: list[float] = []
    logger.warning(
        "semantic_search_degraded",
        reason="embedding service not yet integrated; results use metadata filtering only",
        query_topic=body.topic,
    )
    results = await store.search(
        query_embedding=query_embedding,
        layer=body.layer,
        topic=body.topic,
        content_type=body.content_type,
        limit=body.limit,
    )

    entries = []
    for r in results:
        entries.append(
            KnowledgeEntry(
                id=KnowledgeId(r["id"]),
                layer=r["layer"],
                topic=r.get("topic", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                content_type=r.get("content_type", "documentation"),
                confidence=float(r.get("confidence", 1.0)),
                tags=r.get("tags", []),
                source=r.get("source", ""),
                usage_count=int(r.get("usage_count", 0)),
                active=bool(r.get("active", True)),
            )
        )

    return KnowledgeQueryResult(entries=entries, total=len(entries))


@router.get("/api/v1/knowledge/{knowledge_id}")
async def get_knowledge(
    knowledge_id: str,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict[str, Any]:
    """Retrieve a specific knowledge entry by ID."""
    entry = await store.get_entry(KnowledgeId(knowledge_id))
    if entry is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    # Increment usage counter
    await store.increment_usage(KnowledgeId(knowledge_id))
    return entry


@router.post("/api/v1/knowledge", status_code=201)
async def create_knowledge(
    body: KnowledgeEntry,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict[str, str]:
    """Store a new knowledge entry."""
    await store.store_entry(
        entry_id=body.id,
        layer=body.layer,
        topic=body.topic,
        title=body.title,
        content=body.content,
        content_type=body.content_type,
        confidence=body.confidence,
        tags=list(body.tags),
        embedding=list(body.embedding),
        version_tag=body.version_tag,
        source=body.source,
    )
    return {"id": str(body.id), "status": "created"}


@router.put("/api/v1/knowledge/{knowledge_id}/feedback")
async def knowledge_feedback(
    knowledge_id: str,
    body: FeedbackRequest,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> dict[str, str]:
    """Provide feedback on a knowledge entry."""
    entry = await store.get_entry(KnowledgeId(knowledge_id))
    if entry is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    if body.useful:
        await store.increment_usage(KnowledgeId(knowledge_id))
    else:
        await store.deactivate_entry(KnowledgeId(knowledge_id))

    return {"id": knowledge_id, "status": "feedback_recorded"}


# ── Heuristic endpoints ───────────────────────────────────────────


@router.get("/api/v1/heuristics")
async def list_heuristics(
    domain: str | None = None,
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[dict[str, Any]]:
    """List all active heuristic rules."""
    return await store.get_active_heuristics(domain=domain)


@router.get("/api/v1/heuristics/match")
async def match_heuristics(
    task_type: str | None = None,
    domain: str | None = None,
    engine: HeuristicEngine = Depends(get_heuristic_engine),
) -> list[dict[str, Any]]:
    """Find heuristics matching the given criteria."""
    rules = await engine.match_heuristics(task_type=task_type, domain=domain)
    return [r.model_dump(mode="json") for r in rules]


@router.post("/api/v1/heuristics/{heuristic_id}/outcome")
async def record_heuristic_outcome(
    heuristic_id: str,
    body: HeuristicOutcomeRequest,
    engine: HeuristicEngine = Depends(get_heuristic_engine),
) -> dict[str, str]:
    """Record a success or failure outcome for a heuristic."""
    await engine.evolve_heuristic(HeuristicId(heuristic_id), success=body.success)
    return {"id": heuristic_id, "status": "outcome_recorded"}


# ── Acquisition & compression ─────────────────────────────────────


@router.post("/api/v1/acquire", status_code=202)
async def trigger_acquisition(
    body: AcquireKnowledgeRequest,
) -> dict[str, str]:
    """Trigger a knowledge acquisition workflow (async).

    In production, this would start a Temporal workflow.
    For now, it returns an acknowledgment.
    """
    return {
        "status": "accepted",
        "topic": body.topic,
        "message": "Knowledge acquisition workflow queued.",
    }


@router.post("/api/v1/compress")
async def trigger_compression(
    body: CompressionRequest,
) -> CompressionResult:
    """Trigger the compression pipeline.

    In production, this would start a Temporal workflow.
    For now, it returns an empty result.
    """
    return CompressionResult(
        patterns_created=0,
        heuristics_created=0,
        strategies_proposed=0,
        observations_processed=0,
    )


# ── Working memory endpoints ──────────────────────────────────────


@router.get("/api/v1/working-memory/{task_id}/{agent_id}")
async def get_working_memory_entry(
    task_id: str,
    agent_id: str,
    wm_store: WorkingMemoryStore = Depends(get_working_memory),
) -> dict[str, Any]:
    """Retrieve working memory for a task-agent pair."""
    wm = await wm_store.get(TaskId(task_id), AgentId(agent_id))
    if wm is None:
        raise HTTPException(status_code=404, detail="Working memory not found")
    return wm.model_dump(mode="json")


@router.post("/api/v1/working-memory/{task_id}/{agent_id}")
async def update_working_memory(
    task_id: str,
    agent_id: str,
    body: WorkingMemoryUpdate,
    wm_store: WorkingMemoryStore = Depends(get_working_memory),
) -> dict[str, Any]:
    """Create or update working memory for a task-agent pair."""
    existing = await wm_store.get(TaskId(task_id), AgentId(agent_id))
    if existing is None:
        wm = await wm_store.create(TaskId(task_id), AgentId(agent_id))
    else:
        wm = existing

    context_ids = (
        [KnowledgeId(eid) for eid in body.add_context_entries] if body.add_context_entries else None
    )
    updated = await wm_store.update(
        TaskId(task_id),
        AgentId(agent_id),
        scratchpad_updates=body.scratchpad_updates,
        add_context_entries=context_ids,
    )
    if updated is None:
        return wm.model_dump(mode="json")
    return updated.model_dump(mode="json")


# ── Statistics & meta-strategies ──────────────────────────────────


@router.get("/api/v1/stats", response_model=KnowledgeStats)
async def get_stats(
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> KnowledgeStats:
    """Return aggregate statistics about the knowledge store."""
    raw_stats = await store.get_stats()
    return KnowledgeStats(
        total_entries=raw_stats.get("total_entries", 0),
        entries_by_layer=raw_stats.get("entries_by_layer", {}),
        total_observations=raw_stats.get("total_observations", 0),
        total_heuristics=raw_stats.get("total_heuristics", 0),
        total_meta_strategies=raw_stats.get("total_meta_strategies", 0),
    )


@router.get("/api/v1/meta-strategies")
async def list_meta_strategies(
    store: KnowledgeStore = Depends(get_knowledge_store),
) -> list[dict[str, Any]]:
    """List all meta-strategies."""
    return await store.get_meta_strategies()


# ── Health check ──────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Service health check endpoint."""
    status = HealthStatus.HEALTHY

    try:
        get_knowledge_store()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    try:
        get_working_memory()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    try:
        get_heuristic_engine()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    uptime = time.monotonic() - getattr(request.app.state, "started_at", time.monotonic())
    return HealthResponse(
        service="knowledge-memory",
        status=status,
        uptime_seconds=round(uptime, 2),
    )
