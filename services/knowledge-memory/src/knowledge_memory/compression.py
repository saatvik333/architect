"""Compression pipeline: observations -> patterns -> heuristics -> meta-strategies.

Orchestrates the multi-stage compression of raw observations into progressively
more abstract and actionable knowledge representations.
"""

from __future__ import annotations

from typing import Any

from architect_common.enums import MemoryLayer
from architect_common.logging import get_logger
from architect_common.types import KnowledgeId, new_knowledge_id
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.llm_utils import parse_llm_json_array
from knowledge_memory.models import CompressionResult, MetaStrategy
from knowledge_memory.pattern_extractor import cluster_observations, extract_patterns

logger = get_logger(component="knowledge_memory.compression")


class CompressionPipeline:
    """Orchestrates the full compression pipeline."""

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        heuristic_engine: HeuristicEngine,
        llm_client: LLMClient,
        *,
        min_observations: int = 5,
        min_patterns: int = 3,
    ) -> None:
        self._store = knowledge_store
        self._heuristic_engine = heuristic_engine
        self._llm = llm_client
        self._min_observations = min_observations
        self._min_patterns = min_patterns

    async def compress_observations(
        self,
        *,
        domain: str | None = None,
    ) -> CompressionResult:
        """Run the full compression pipeline for a domain.

        1. Fetch uncompressed observations
        2. Cluster by embedding similarity
        3. Extract patterns from each cluster via LLM
        4. Store patterns and mark observations as compressed
        """
        observations = await self._store.get_uncompressed_observations(
            domain=domain,
            min_count=self._min_observations,
        )

        if not observations:
            logger.info("no observations to compress", domain=domain)
            return CompressionResult()

        # Cluster observations
        clusters = cluster_observations(observations)
        logger.info(
            "clustered observations",
            total_observations=len(observations),
            cluster_count=len(clusters),
        )

        total_patterns = 0
        for cluster in clusters:
            if len(cluster) < 2:
                continue

            # Extract patterns from this cluster
            patterns = await extract_patterns(cluster, self._llm)

            # Store each pattern and track their IDs for observation linkage
            stored_pattern_ids: list[KnowledgeId] = []
            for pattern in patterns:
                stored_id = (
                    KnowledgeId(pattern.id) if hasattr(pattern, "id") else new_knowledge_id()
                )
                await self._store.store_entry(
                    entry_id=stored_id,
                    layer=pattern.layer,
                    topic=pattern.topic,
                    title=pattern.title,
                    content=pattern.content,
                    content_type=pattern.content_type,
                    confidence=pattern.confidence,
                    tags=list(pattern.tags),
                    embedding=list(pattern.embedding),
                    source=pattern.source,
                )
                stored_pattern_ids.append(stored_id)
                total_patterns += 1

            # Link observations to the first stored pattern in the cluster
            obs_ids = [KnowledgeId(o["id"]) for o in cluster]
            link_id = stored_pattern_ids[0] if stored_pattern_ids else new_knowledge_id()
            await self._store.mark_observations_compressed(obs_ids, link_id)

        return CompressionResult(
            patterns_created=total_patterns,
            observations_processed=len(observations),
        )

    async def promote_patterns_to_heuristics(
        self,
        *,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Synthesize heuristic rules from existing patterns.

        Fetches L2 pattern entries and uses the heuristic engine to
        synthesize actionable rules at L3.
        """
        # Fetch pattern-layer entries
        patterns_raw = await self._store.search(
            query_embedding=[],
            layer=MemoryLayer.L2_PATTERN,
            topic=domain,
            limit=50,
        )

        if len(patterns_raw) < self._min_patterns:
            logger.info(
                "not enough patterns for heuristic synthesis",
                pattern_count=len(patterns_raw),
                min_required=self._min_patterns,
            )
            return []

        rules = await self._heuristic_engine.synthesize_heuristics(patterns_raw)

        stored_rules: list[dict[str, Any]] = []
        for rule in rules:
            rule_dict = rule.model_dump(mode="json")
            await self._store.store_heuristic(rule_dict)
            stored_rules.append(rule_dict)

        logger.info("promoted patterns to heuristics", count=len(stored_rules))
        return stored_rules

    async def derive_meta_strategies(self) -> list[MetaStrategy]:
        """Derive high-level meta-strategies from existing heuristics.

        Uses LLM to analyze the full set of active heuristics and propose
        overarching strategies that combine multiple rules.
        """
        heuristics = await self._store.get_active_heuristics()

        if not heuristics:
            logger.info("no heuristics available for meta-strategy derivation")
            return []

        heuristic_summaries = []
        for h in heuristics:
            heuristic_summaries.append(
                f"- [{h.get('domain', 'general')}] "
                f"IF {h.get('condition', '?')} THEN {h.get('action', '?')} "
                f"(confidence: {h.get('confidence', 0):.2f})"
            )

        heuristic_text = "\n".join(heuristic_summaries)

        request = LLMRequest(
            system_prompt=(
                "You are an expert software engineering strategist. "
                "Given a set of heuristic rules, derive high-level meta-strategies "
                "that combine multiple rules into coherent approaches. "
                "Return a JSON array of strategy objects with keys: "
                '"name", "description", "applicable_task_types" (array of strings), '
                '"steps" (array of strings), "confidence" (0-1 float).'
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Heuristic rules ({len(heuristics)} total):\n<user_input>{heuristic_text}</user_input>\n\n"
                        "Derive meta-strategies from these heuristics. "
                        "Return ONLY a JSON array."
                    ),
                }
            ],
            max_tokens=4000,
            temperature=0.3,
        )

        response = await self._llm.generate(request)

        strategies: list[MetaStrategy] = []
        heuristic_ids = [h["id"] for h in heuristics if "id" in h]

        for rs in parse_llm_json_array(response.content, logger):
            strategy = MetaStrategy(
                id=new_knowledge_id(),
                name=rs.get("name", "Unnamed strategy"),
                description=rs.get("description", ""),
                applicable_task_types=[],  # TaskType validation deferred
                steps=rs.get("steps", []),
                source_heuristic_ids=heuristic_ids[:5],  # Link top heuristics
                confidence=float(rs.get("confidence", 0.5)),
            )
            strategies.append(strategy)

            # Store the strategy
            await self._store.store_meta_strategy(strategy.model_dump(mode="json"))

        logger.info("derived meta-strategies", count=len(strategies))
        return strategies
