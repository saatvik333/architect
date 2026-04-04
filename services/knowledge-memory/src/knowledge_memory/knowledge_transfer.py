"""Cross-project knowledge transfer for the Knowledge & Memory system.

Identifies heuristics that have been independently discovered in multiple
projects and promotes them to global scope. Also creates project-scoped
overrides when global heuristics start failing in specific projects.
"""

from __future__ import annotations

from architect_common.logging import get_logger
from architect_common.types import new_heuristic_id
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.models import HeuristicRule

logger = get_logger(component="knowledge_transfer")


async def find_cross_project_heuristics(
    heuristic_engine: HeuristicEngine,
    min_project_count: int = 2,
) -> list[list[HeuristicRule]]:
    """Find heuristics independently discovered in multiple projects.

    Groups heuristics by similar condition+action across different project_ids.
    Returns groups of related heuristics (each group has entries from different
    projects describing similar rules).
    """
    all_heuristics = await heuristic_engine.match_heuristics()

    # Group by domain for efficiency
    by_domain: dict[str, list[HeuristicRule]] = {}
    for h in all_heuristics:
        if not h.project_id:
            continue  # Skip already-global heuristics
        by_domain.setdefault(h.domain, []).append(h)

    groups: list[list[HeuristicRule]] = []

    for domain, heuristics in by_domain.items():
        # Simple grouping: heuristics with identical conditions
        by_condition: dict[str, list[HeuristicRule]] = {}
        for h in heuristics:
            key = h.condition.strip().lower()
            by_condition.setdefault(key, []).append(h)

        for condition, group in by_condition.items():
            # Count distinct project_ids
            project_ids = {h.project_id for h in group}
            if len(project_ids) >= min_project_count:
                groups.append(group)
                logger.info(
                    "cross_project_heuristic_found",
                    domain=domain,
                    condition=condition[:80],
                    project_count=len(project_ids),
                )

    return groups


async def promote_to_global(
    store: KnowledgeStore,
    heuristic_group: list[HeuristicRule],
    confidence_boost: float = 0.1,
) -> HeuristicRule | None:
    """Promote a group of project-scoped heuristics to global scope.

    Creates a new global heuristic (project_id="") with boosted confidence,
    using the highest-confidence entry from the group as the template.
    """
    if not heuristic_group:
        return None

    # Pick the highest-confidence entry as the template
    best = max(heuristic_group, key=lambda h: h.confidence)

    global_heuristic = HeuristicRule(
        id=new_heuristic_id(),
        domain=best.domain,
        condition=best.condition,
        action=best.action,
        rationale=f"Promoted from {len(heuristic_group)} projects: {best.rationale}",
        confidence=min(best.confidence + confidence_boost, 1.0),
        success_count=sum(h.success_count for h in heuristic_group),
        failure_count=sum(h.failure_count for h in heuristic_group),
        active=True,
        project_id="",  # Global scope
        source_pattern_ids=best.source_pattern_ids,
    )

    await store.store_heuristic(global_heuristic.model_dump())
    logger.info(
        "heuristic_promoted_to_global",
        heuristic_id=str(global_heuristic.id),
        domain=best.domain,
        source_projects=len(heuristic_group),
    )
    return global_heuristic


async def run_knowledge_transfer(
    heuristic_engine: HeuristicEngine,
    store: KnowledgeStore,
    min_project_count: int = 2,
) -> int:
    """Run the full cross-project knowledge transfer pipeline.

    Returns the number of heuristics promoted to global scope.
    """
    groups = await find_cross_project_heuristics(
        heuristic_engine,
        min_project_count=min_project_count,
    )

    promoted = 0
    for group in groups:
        result = await promote_to_global(store, group)
        if result:
            promoted += 1

    logger.info(
        "knowledge_transfer_complete",
        groups_found=len(groups),
        promoted=promoted,
    )
    return promoted
