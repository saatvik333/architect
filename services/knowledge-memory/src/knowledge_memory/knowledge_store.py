"""Core data access layer for knowledge entries and observations.

Uses SQLAlchemy async sessions for PostgreSQL access.  Embeddings are stored
as JSONB arrays and cosine similarity is computed in Python (avoiding a hard
dependency on the pgvector extension for the MVP).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from architect_common.enums import ContentType, MemoryLayer, ObservationType
from architect_common.logging import get_logger
from architect_common.types import (
    AgentId,
    HeuristicId,
    KnowledgeId,
    PatternId,
    TaskId,
    utcnow,
)
from knowledge_memory.similarity import cosine_similarity

logger = get_logger(component="knowledge_memory.knowledge_store")


class KnowledgeStore:
    """Persistent store for knowledge entries, observations, and heuristics.

    Uses raw SQL via SQLAlchemy ``text()`` to stay close to the metal
    while keeping the async interface clean.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Knowledge entries ────────────────────────────────────────────

    async def store_entry(
        self,
        *,
        entry_id: KnowledgeId,
        layer: MemoryLayer,
        topic: str,
        title: str,
        content: str,
        content_type: ContentType,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        version_tag: str = "",
        source: str = "",
    ) -> None:
        """Insert or update a knowledge entry."""
        now = utcnow()
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO knowledge_entries
                        (id, layer, topic, title, content, content_type,
                         confidence, tags, embedding, version_tag, source,
                         usage_count, active, created_at, updated_at)
                    VALUES
                        (:id, :layer, :topic, :title, :content, :content_type,
                         :confidence, :tags::jsonb, :embedding::jsonb, :version_tag, :source,
                         0, true, :now, :now)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        confidence = EXCLUDED.confidence,
                        tags = EXCLUDED.tags,
                        embedding = EXCLUDED.embedding,
                        version_tag = EXCLUDED.version_tag,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(entry_id),
                    "layer": layer.value,
                    "topic": topic,
                    "title": title,
                    "content": content,
                    "content_type": content_type.value,
                    "confidence": confidence,
                    "tags": _to_json(tags or []),
                    "embedding": _to_json(embedding or []),
                    "version_tag": version_tag,
                    "source": source,
                    "now": now,
                },
            )
            await session.commit()
        logger.info("stored knowledge entry", entry_id=str(entry_id), layer=layer.value)

    async def get_entry(self, entry_id: KnowledgeId) -> dict[str, Any] | None:
        """Retrieve a single knowledge entry by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM knowledge_entries WHERE id = :id"),
                {"id": str(entry_id)},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    async def search(
        self,
        query_embedding: list[float],
        *,
        layer: MemoryLayer | None = None,
        topic: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search knowledge entries by cosine similarity.

        Fetches active entries (optionally filtered by layer/topic/content_type)
        and ranks them by cosine similarity to *query_embedding* in Python.

        When *query_embedding* is empty, similarity ranking is skipped and results
        are returned in insertion order (useful for filter-only queries).
        """
        conditions = ["active = true"]
        params: dict[str, Any] = {}

        if layer is not None:
            conditions.append("layer = :layer")
            params["layer"] = layer.value
        if topic is not None:
            conditions.append("topic = :topic")
            params["topic"] = topic
        if content_type is not None:
            conditions.append("content_type = :content_type")
            params["content_type"] = content_type.value

        where = " AND ".join(conditions)

        # When no embedding is provided, skip similarity ranking and limit at the DB level.
        if not query_embedding:
            query = f"SELECT * FROM knowledge_entries WHERE {where} LIMIT :limit"
            params["limit"] = limit
            async with self._session_factory() as session:
                result = await session.execute(text(query), params)
                return [dict(r) for r in result.mappings().all()]

        query = f"SELECT * FROM knowledge_entries WHERE {where}"

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            rows = [dict(r) for r in result.mappings().all()]

        # Rank by cosine similarity
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            emb = row.get("embedding") or []
            if isinstance(emb, str):
                emb = json.loads(emb)
            sim = cosine_similarity(query_embedding, emb)
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[:limit]]

    async def increment_usage(self, entry_id: KnowledgeId) -> None:
        """Bump the usage counter for a knowledge entry."""
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE knowledge_entries
                    SET usage_count = usage_count + 1, updated_at = :now
                    WHERE id = :id
                """),
                {"id": str(entry_id), "now": utcnow()},
            )
            await session.commit()

    async def deactivate_entry(self, entry_id: KnowledgeId) -> None:
        """Soft-delete a knowledge entry by marking it inactive."""
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE knowledge_entries
                    SET active = false, updated_at = :now
                    WHERE id = :id
                """),
                {"id": str(entry_id), "now": utcnow()},
            )
            await session.commit()

    # ── Observations ─────────────────────────────────────────────────

    async def store_observation(
        self,
        *,
        obs_id: KnowledgeId,
        task_id: TaskId,
        agent_id: AgentId,
        observation_type: ObservationType,
        description: str,
        context: dict[str, object] | None = None,
        outcome: str = "",
        domain: str = "",
        embedding: list[float] | None = None,
    ) -> None:
        """Store a raw observation from task execution."""
        now = utcnow()
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO observations
                        (id, task_id, agent_id, observation_type, description,
                         context, outcome, domain, embedding, compressed,
                         pattern_id, created_at)
                    VALUES
                        (:id, :task_id, :agent_id, :observation_type, :description,
                         :context::jsonb, :outcome, :domain, :embedding::jsonb, false,
                         NULL, :now)
                """),
                {
                    "id": str(obs_id),
                    "task_id": str(task_id),
                    "agent_id": str(agent_id),
                    "observation_type": observation_type.value,
                    "description": description,
                    "context": _to_json(context or {}),
                    "outcome": outcome,
                    "domain": domain,
                    "embedding": _to_json(embedding or []),
                    "now": now,
                },
            )
            await session.commit()
        logger.info(
            "stored observation", obs_id=str(obs_id), observation_type=observation_type.value
        )

    async def get_uncompressed_observations(
        self,
        *,
        domain: str | None = None,
        min_count: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch uncompressed observations, optionally filtered by domain.

        Returns observations only when there are at least *min_count* available.
        """
        conditions = ["compressed = false"]
        params: dict[str, Any] = {}

        if domain is not None:
            conditions.append("domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        query = f"SELECT * FROM observations WHERE {where} ORDER BY created_at"

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            rows = [dict(r) for r in result.mappings().all()]

        if len(rows) < min_count:
            return []
        return rows

    async def mark_observations_compressed(
        self,
        obs_ids: list[KnowledgeId],
        pattern_id: PatternId,
    ) -> None:
        """Mark a set of observations as compressed under a given pattern."""
        if not obs_ids:
            return
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE observations
                    SET compressed = true, pattern_id = :pattern_id
                    WHERE id = ANY(:ids)
                """),
                {
                    "pattern_id": str(pattern_id),
                    "ids": [str(oid) for oid in obs_ids],
                },
            )
            await session.commit()

    # ── Heuristics ───────────────────────────────────────────────────

    async def store_heuristic(self, heuristic: dict[str, Any]) -> None:
        """Store a heuristic rule."""
        now = utcnow()
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO heuristics
                        (id, domain, condition, action, rationale, confidence,
                         success_count, failure_count, active,
                         source_pattern_ids, created_at)
                    VALUES
                        (:id, :domain, :condition, :action, :rationale, :confidence,
                         :success_count, :failure_count, true,
                         :source_pattern_ids::jsonb, :now)
                    ON CONFLICT (id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        success_count = EXCLUDED.success_count,
                        failure_count = EXCLUDED.failure_count
                """),
                {
                    "id": heuristic["id"],
                    "domain": heuristic.get("domain", ""),
                    "condition": heuristic.get("condition", ""),
                    "action": heuristic.get("action", ""),
                    "rationale": heuristic.get("rationale", ""),
                    "confidence": heuristic.get("confidence", 0.5),
                    "success_count": heuristic.get("success_count", 0),
                    "failure_count": heuristic.get("failure_count", 0),
                    "source_pattern_ids": _to_json(heuristic.get("source_pattern_ids", [])),
                    "now": now,
                },
            )
            await session.commit()

    async def get_active_heuristics(
        self,
        *,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all active heuristic rules, optionally filtered by domain."""
        conditions = ["active = true"]
        params: dict[str, Any] = {}

        if domain is not None:
            conditions.append("domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        query = f"SELECT * FROM heuristics WHERE {where} ORDER BY confidence DESC"

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            return [dict(r) for r in result.mappings().all()]

    async def update_heuristic_outcome(
        self,
        heuristic_id: HeuristicId,
        *,
        success: bool,
    ) -> None:
        """Record an outcome for a heuristic, updating counters and confidence."""
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE heuristics
                    SET success_count = success_count + CASE WHEN :is_success THEN 1 ELSE 0 END,
                        failure_count = failure_count + CASE WHEN :is_success THEN 0 ELSE 1 END,
                        confidence = CASE
                            WHEN (success_count + failure_count + 1) > 0
                            THEN (success_count + CASE WHEN :is_success THEN 1 ELSE 0 END)::float
                                 / (success_count + failure_count + 1)::float
                            ELSE confidence
                        END
                    WHERE id = :id
                """),
                {"id": str(heuristic_id), "is_success": success},
            )
            await session.commit()

    # ── Meta-strategies ──────────────────────────────────────────────

    async def store_meta_strategy(self, strategy: dict[str, Any]) -> None:
        """Store a meta-strategy."""
        now = utcnow()
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO meta_strategies
                        (id, name, description, applicable_task_types, steps,
                         source_heuristic_ids, confidence, created_at)
                    VALUES
                        (:id, :name, :description, :applicable_task_types::jsonb,
                         :steps::jsonb, :source_heuristic_ids::jsonb, :confidence, :now)
                    ON CONFLICT (id) DO UPDATE SET
                        description = EXCLUDED.description,
                        steps = EXCLUDED.steps,
                        confidence = EXCLUDED.confidence
                """),
                {
                    "id": strategy["id"],
                    "name": strategy.get("name", ""),
                    "description": strategy.get("description", ""),
                    "applicable_task_types": _to_json(strategy.get("applicable_task_types", [])),
                    "steps": _to_json(strategy.get("steps", [])),
                    "source_heuristic_ids": _to_json(strategy.get("source_heuristic_ids", [])),
                    "confidence": strategy.get("confidence", 0.5),
                    "now": now,
                },
            )
            await session.commit()

    async def get_meta_strategies(self) -> list[dict[str, Any]]:
        """Fetch all meta-strategies."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM meta_strategies ORDER BY confidence DESC")
            )
            return [dict(r) for r in result.mappings().all()]

    # ── Statistics ───────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the knowledge store.

        Uses a single query with sub-selects to avoid 5 sequential round-trips.
        """
        async with self._session_factory() as session:
            # Combine all counts into a single round-trip
            counts_res = await session.execute(
                text("""
                    SELECT
                        (SELECT COUNT(*) FROM knowledge_entries WHERE active = true) AS total_entries,
                        (SELECT COUNT(*) FROM observations) AS total_observations,
                        (SELECT COUNT(*) FROM heuristics WHERE active = true) AS total_heuristics,
                        (SELECT COUNT(*) FROM meta_strategies) AS total_meta_strategies
                """)
            )
            counts = counts_res.mappings().first()

            # Layer breakdown still needs GROUP BY
            layer_res = await session.execute(
                text("""
                    SELECT layer, COUNT(*) AS cnt
                    FROM knowledge_entries
                    WHERE active = true
                    GROUP BY layer
                """)
            )
            entries_by_layer = {row.layer: row.cnt for row in layer_res}

        return {
            "total_entries": counts["total_entries"] if counts else 0,
            "entries_by_layer": entries_by_layer,
            "total_observations": counts["total_observations"] if counts else 0,
            "total_heuristics": counts["total_heuristics"] if counts else 0,
            "total_meta_strategies": counts["total_meta_strategies"] if counts else 0,
        }


def _to_json(obj: Any) -> str:
    """Serialize a Python object to a JSON string for JSONB columns."""
    return json.dumps(obj)
