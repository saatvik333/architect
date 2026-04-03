"""Temporal activity definitions for the Failure Taxonomy service.

Activities are defined as methods on :class:`FailureTaxonomyActivities` so
that the Temporal worker can inject shared classifier, analyzer, and
session factory instances.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.enums import ImprovementType, PostMortemStatus
from architect_common.logging import get_logger
from architect_common.types import new_failure_record_id, new_improvement_id, utcnow
from architect_db.models.failure import FailureRecord, Improvement, PostMortem
from architect_db.repositories.failure_repo import (
    FailureRecordRepository,
    ImprovementRepository,
    PostMortemRepository,
)
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.models import ClassificationRequest, SimulationConfig
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer
from failure_taxonomy.simulation_runner import SimulationRunner

logger = get_logger(component="failure_taxonomy.temporal.activities")


class FailureTaxonomyActivities:
    """Temporal activities that operate on shared Failure Taxonomy state."""

    def __init__(
        self,
        classifier: FailureClassifier,
        post_mortem_analyzer: PostMortemAnalyzer,
        simulation_runner: SimulationRunner,
        session_factory: Any,
    ) -> None:
        self._classifier = classifier
        self._analyzer = post_mortem_analyzer
        self._runner = simulation_runner
        self._session_factory = session_factory

    @activity.defn
    async def classify_failure(self, params: dict[str, Any]) -> dict[str, Any]:
        """Classify a failure and persist the record.

        Args:
            params: Dict with classification request fields.

        Returns:
            Dict with failure_record_id, failure_code, confidence, summary.
        """
        activity.logger.info("classify_failure activity started")

        request = ClassificationRequest(
            task_id=params.get("task_id", ""),
            agent_id=params.get("agent_id"),
            error_message=params.get("error_message", ""),
            stack_trace=params.get("stack_trace"),
            eval_layer=params.get("eval_layer"),
            code_context=params.get("code_context"),
        )

        classification = await self._classifier.classify(request)

        # Persist the record
        record_id = new_failure_record_id()
        async with self._session_factory() as session:
            repo = FailureRecordRepository(session)
            record = FailureRecord(
                id=record_id,
                task_id=request.task_id,
                agent_id=request.agent_id,
                failure_code=classification.failure_code.value,
                severity="medium",
                summary=classification.summary,
                root_cause=classification.root_cause,
                eval_layer=request.eval_layer,
                error_message=request.error_message[:2000] if request.error_message else None,
                classified_by="auto",
                confidence=classification.confidence,
            )
            await repo.create(record)
            await session.commit()

        return {
            "failure_record_id": record_id,
            "failure_code": classification.failure_code.value,
            "confidence": classification.confidence,
            "summary": classification.summary,
        }

    @activity.defn
    async def run_post_mortem(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run post-mortem analysis for a project.

        Args:
            params: Dict with project_id and optional task_id.

        Returns:
            Dict with post_mortem_id, failure_count, improvements_proposed.
        """
        activity.logger.info("run_post_mortem activity started")

        project_id = params.get("project_id", "")

        async with self._session_factory() as session:
            failure_repo = FailureRecordRepository(session)
            pm_repo = PostMortemRepository(session)
            imp_repo = ImprovementRepository(session)

            failures = await failure_repo.get_by_project(project_id, limit=200)
            unresolved = [f for f in failures if not f.resolved]

            if not unresolved:
                return {
                    "post_mortem_id": "",
                    "failure_count": 0,
                    "improvements_proposed": 0,
                }

            analysis = await self._analyzer.analyze(project_id, unresolved)

            pm = PostMortem(
                id=str(analysis.post_mortem_id),
                project_id=project_id,
                task_id=params.get("task_id"),
                status=PostMortemStatus.COMPLETED,
                failure_count=len(unresolved),
                failure_breakdown=analysis.failure_summary,
                root_causes=analysis.root_causes,
                prompt_improvements=[
                    p.model_dump(mode="json") for p in analysis.prompt_improvements
                ],
                new_adversarial_tests=[
                    t.model_dump(mode="json") for t in analysis.adversarial_tests
                ],
                heuristic_updates=[h.model_dump(mode="json") for h in analysis.heuristic_updates],
                topology_recommendations=[
                    r.model_dump(mode="json") for r in analysis.topology_recommendations
                ],
                completed_at=utcnow(),
            )
            await pm_repo.create(pm)

            improvements_count = 0
            for pi in analysis.prompt_improvements:
                imp = Improvement(
                    id=new_improvement_id(),
                    post_mortem_id=pm.id,
                    improvement_type=ImprovementType.PROMPT_IMPROVEMENT,
                    description=pi.suggested_change,
                    content=pi.model_dump(mode="json"),
                )
                await imp_repo.create(imp)
                improvements_count += 1

            for at in analysis.adversarial_tests:
                imp = Improvement(
                    id=new_improvement_id(),
                    post_mortem_id=pm.id,
                    improvement_type=ImprovementType.ADVERSARIAL_TEST,
                    description=at.test_description,
                    content=at.model_dump(mode="json"),
                )
                await imp_repo.create(imp)
                improvements_count += 1

            for hu in analysis.heuristic_updates:
                imp = Improvement(
                    id=new_improvement_id(),
                    post_mortem_id=pm.id,
                    improvement_type=ImprovementType.HEURISTIC_UPDATE,
                    description=hu.action,
                    content=hu.model_dump(mode="json"),
                )
                await imp_repo.create(imp)
                improvements_count += 1

            for tr in analysis.topology_recommendations:
                imp = Improvement(
                    id=new_improvement_id(),
                    post_mortem_id=pm.id,
                    improvement_type=ImprovementType.TOPOLOGY_RECOMMENDATION,
                    description=tr.recommendation,
                    content=tr.model_dump(mode="json"),
                )
                await imp_repo.create(imp)
                improvements_count += 1

            await session.commit()

        return {
            "post_mortem_id": pm.id,
            "failure_count": len(unresolved),
            "improvements_proposed": improvements_count,
        }

    @activity.defn
    async def run_simulation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a simulation training exercise.

        Args:
            params: Dict with simulation config fields.

        Returns:
            Dict with simulation_id, detection_rate, and results.
        """
        activity.logger.info("run_simulation activity started")

        config = SimulationConfig(
            source_type=params.get("source_type", "manual"),
            source_ref=params.get("source_ref", ""),
            bug_injection_count=params.get("bug_injection_count", 5),
            max_duration_seconds=params.get("max_duration_seconds", 300),
        )

        result = await self._runner.run_simulation(config)

        return {
            "simulation_id": "",
            "detection_rate": result.detection_rate,
            "failures_injected": result.failures_injected,
            "failures_detected": result.failures_detected,
        }

    @activity.defn
    async def get_failure_stats(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get failure statistics for reporting.

        Args:
            params: Dict with optional project_id filter.

        Returns:
            Dict with stats by failure code and total count.
        """
        activity.logger.info("get_failure_stats activity started")

        async with self._session_factory() as session:
            repo = FailureRecordRepository(session)
            stats = await repo.get_stats_by_code()

        return {
            "stats": stats,
            "total": sum(stats.values()),
        }
