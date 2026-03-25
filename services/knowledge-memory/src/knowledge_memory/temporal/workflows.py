"""Temporal workflow definitions for the Knowledge & Memory service."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from knowledge_memory.temporal.activities import (
        cluster_observations_activity,
        compress_cluster_activity,
        derive_meta_strategies_activity,
        fetch_documentation_activity,
        fetch_uncompressed_observations_activity,
        mine_examples_activity,
        publish_knowledge_update_activity,
        store_knowledge_activity,
        summarize_documentation_activity,
        synthesize_heuristics_activity,
        tag_versions_activity,
    )


@workflow.defn
class KnowledgeAcquisitionWorkflow:
    """Workflow for acquiring new knowledge from external sources.

    Steps:
        1. Fetch documentation from provided URLs
        2. Summarize the documentation
        3. Mine code examples
        4. Apply version tags
        5. Store in knowledge base
        6. Publish knowledge update event
    """

    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the knowledge acquisition pipeline."""
        topic = params.get("topic", "general")
        source_urls = params.get("source_urls", [])
        version_tag = params.get("version_tag", "")
        tags = params.get("tags", [])

        results: list[dict[str, Any]] = []

        # Step 1 & 2: Fetch and summarize documentation from each URL
        for url in source_urls:
            fetch_result = await workflow.execute_activity(
                fetch_documentation_activity,
                {"url": url, "max_size_kb": 500},
                start_to_close_timeout=timedelta(seconds=60),
            )

            summary_result = await workflow.execute_activity(
                summarize_documentation_activity,
                {
                    "content": fetch_result["content"],
                    "topic": topic,
                    "url": url,
                },
                start_to_close_timeout=timedelta(seconds=120),
            )

            # Step 4: Tag with version if provided
            entry_data = {
                "id": "",
                "layer": "l1_project",
                "topic": topic,
                "title": summary_result["title"],
                "content": summary_result["summary"],
                "content_type": "documentation",
                "tags": tags + summary_result.get("tags", []),
            }

            if version_tag:
                tagged = await workflow.execute_activity(
                    tag_versions_activity,
                    {"entry": entry_data, "version_tag": version_tag},
                    start_to_close_timeout=timedelta(seconds=30),
                )
                entry_data = tagged

            # Step 5: Store
            store_result = await workflow.execute_activity(
                store_knowledge_activity,
                entry_data,
                start_to_close_timeout=timedelta(seconds=30),
            )

            results.append(store_result)

        # Step 3: Mine examples
        if topic:
            mine_result = await workflow.execute_activity(
                mine_examples_activity,
                {"topic": topic, "source_urls": source_urls},
                start_to_close_timeout=timedelta(seconds=120),
            )

            for example in mine_result.get("examples", []):
                store_result = await workflow.execute_activity(
                    store_knowledge_activity,
                    example,
                    start_to_close_timeout=timedelta(seconds=30),
                )
                results.append(store_result)

        # Step 6: Publish knowledge update event
        if results:
            await workflow.execute_activity(
                publish_knowledge_update_activity,
                {
                    "knowledge_id": results[0].get("id", ""),
                    "topic": topic,
                    "source": "acquisition_workflow",
                },
                start_to_close_timeout=timedelta(seconds=30),
            )

        return {
            "topic": topic,
            "entries_created": len(results),
            "results": results,
        }


@workflow.defn
class CompressionWorkflow:
    """Workflow for compressing observations into patterns, heuristics, and strategies.

    Steps:
        1. Fetch uncompressed observations
        2. Cluster observations by similarity
        3. Extract patterns from each cluster
        4. Synthesize heuristics from patterns
        5. Derive meta-strategies from heuristics
    """

    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the compression pipeline."""
        domain = params.get("domain")

        # Step 1: Fetch uncompressed observations
        obs_result = await workflow.execute_activity(
            fetch_uncompressed_observations_activity,
            {"domain": domain, "min_count": 5},
            start_to_close_timeout=timedelta(seconds=30),
        )

        observations = obs_result.get("observations", [])
        if not observations:
            return {
                "patterns_created": 0,
                "heuristics_created": 0,
                "strategies_proposed": 0,
                "observations_processed": 0,
            }

        # Step 2: Cluster observations
        cluster_result = await workflow.execute_activity(
            cluster_observations_activity,
            {"observations": observations},
            start_to_close_timeout=timedelta(seconds=60),
        )

        clusters = cluster_result.get("clusters", [])
        all_patterns: list[dict[str, Any]] = []

        # Step 3: Extract patterns from each cluster
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            pattern_result = await workflow.execute_activity(
                compress_cluster_activity,
                {"cluster": cluster},
                start_to_close_timeout=timedelta(seconds=120),
            )
            all_patterns.extend(pattern_result.get("patterns", []))

        # Step 4: Synthesize heuristics
        heuristic_result = await workflow.execute_activity(
            synthesize_heuristics_activity,
            {"patterns": all_patterns},
            start_to_close_timeout=timedelta(seconds=120),
        )

        heuristics = heuristic_result.get("heuristics", [])

        # Step 5: Derive meta-strategies
        strategy_result = await workflow.execute_activity(
            derive_meta_strategies_activity,
            {"heuristics": heuristics},
            start_to_close_timeout=timedelta(seconds=120),
        )

        strategies = strategy_result.get("strategies", [])

        return {
            "patterns_created": len(all_patterns),
            "heuristics_created": len(heuristics),
            "strategies_proposed": len(strategies),
            "observations_processed": len(observations),
        }
