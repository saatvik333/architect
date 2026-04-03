"""Temporal workflow definitions for the Failure Taxonomy service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

TASK_QUEUE = "failure-taxonomy"

# Activity name constants — correspond to methods on
# ``failure_taxonomy.temporal.activities.FailureTaxonomyActivities``.
ACT_CLASSIFY_FAILURE = "classify_failure"
ACT_RUN_POST_MORTEM = "run_post_mortem"
ACT_RUN_SIMULATION = "run_simulation"
ACT_GET_FAILURE_STATS = "get_failure_stats"


# ── Typed workflow parameters ────────────────────────────────────────


@dataclass
class ClassificationParams:
    """Input for the failure classification workflow."""

    task_id: str = ""
    agent_id: str | None = None
    error_message: str = ""
    stack_trace: str | None = None
    eval_layer: str | None = None
    eval_report: dict[str, Any] | None = None
    code_context: str | None = None


@dataclass
class ClassificationResult:
    """Output of the failure classification workflow."""

    failure_record_id: str = ""
    failure_code: str = ""
    confidence: float = 0.0
    summary: str = ""


@dataclass
class PostMortemParams:
    """Input for the post-mortem analysis workflow."""

    project_id: str = ""
    task_id: str | None = None
    min_failures: int = 1


@dataclass
class PostMortemResult:
    """Output of the post-mortem analysis workflow."""

    post_mortem_id: str = ""
    failure_count: int = 0
    improvements_proposed: int = 0
    completed: bool = False


@dataclass
class SimulationTrainingParams:
    """Input for the simulation training workflow."""

    source_type: str = "manual"
    source_ref: str = ""
    bug_injection_count: int = 5
    max_duration_seconds: int = 300


@dataclass
class SimulationTrainingResult:
    """Output of the simulation training workflow."""

    simulation_id: str = ""
    detection_rate: float = 0.0
    completed: bool = False


@workflow.defn
class FailureClassificationWorkflow:
    """One-shot workflow that classifies a failure and persists the record.

    Invoked when a failure event is received and classification needs to
    be durable (e.g., from a Temporal signal or scheduled trigger).
    """

    @workflow.run
    async def run(self, params: ClassificationParams | dict[str, Any]) -> ClassificationResult:
        """Classify a failure via the classification activity.

        Args:
            params: Classification parameters or dict for backwards compat.

        Returns:
            :class:`ClassificationResult` with the failure record ID and code.
        """
        if isinstance(params, dict):
            params = ClassificationParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in ClassificationParams.__dataclass_fields__
                }
            )

        result: dict[str, Any] = await workflow.execute_activity(
            ACT_CLASSIFY_FAILURE,
            args=[
                {
                    "task_id": params.task_id,
                    "agent_id": params.agent_id,
                    "error_message": params.error_message,
                    "stack_trace": params.stack_trace,
                    "eval_layer": params.eval_layer,
                    "code_context": params.code_context,
                }
            ],
            start_to_close_timeout=timedelta(seconds=60),
        )

        return ClassificationResult(
            failure_record_id=result.get("failure_record_id", ""),
            failure_code=result.get("failure_code", ""),
            confidence=result.get("confidence", 0.0),
            summary=result.get("summary", ""),
        )


@workflow.defn
class PostMortemWorkflow:
    """Workflow that runs post-mortem analysis for a project.

    Fetches failure statistics, runs the analysis, and persists improvements.
    """

    @workflow.run
    async def run(self, params: PostMortemParams | dict[str, Any]) -> PostMortemResult:
        """Execute the post-mortem analysis.

        Args:
            params: Post-mortem parameters or dict for backwards compat.

        Returns:
            :class:`PostMortemResult` with analysis summary.
        """
        if isinstance(params, dict):
            params = PostMortemParams(
                **{k: v for k, v in params.items() if k in PostMortemParams.__dataclass_fields__}
            )

        # Step 1: Get failure stats to check if post-mortem is warranted
        stats: dict[str, Any] = await workflow.execute_activity(
            ACT_GET_FAILURE_STATS,
            args=[{"project_id": params.project_id}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        total_failures = stats.get("total", 0)
        if total_failures < params.min_failures:
            return PostMortemResult(
                completed=False,
            )

        # Step 2: Run the post-mortem analysis
        result: dict[str, Any] = await workflow.execute_activity(
            ACT_RUN_POST_MORTEM,
            args=[
                {
                    "project_id": params.project_id,
                    "task_id": params.task_id,
                }
            ],
            start_to_close_timeout=timedelta(seconds=120),
        )

        return PostMortemResult(
            post_mortem_id=result.get("post_mortem_id", ""),
            failure_count=result.get("failure_count", 0),
            improvements_proposed=result.get("improvements_proposed", 0),
            completed=True,
        )


@workflow.defn
class SimulationTrainingWorkflow:
    """Workflow that runs a simulation training exercise.

    Injects known bugs and evaluates the system's detection accuracy.
    """

    @workflow.run
    async def run(
        self, params: SimulationTrainingParams | dict[str, Any]
    ) -> SimulationTrainingResult:
        """Execute a simulation training run.

        Args:
            params: Simulation parameters or dict for backwards compat.

        Returns:
            :class:`SimulationTrainingResult` with detection metrics.
        """
        if isinstance(params, dict):
            params = SimulationTrainingParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in SimulationTrainingParams.__dataclass_fields__
                }
            )

        result: dict[str, Any] = await workflow.execute_activity(
            ACT_RUN_SIMULATION,
            args=[
                {
                    "source_type": params.source_type,
                    "source_ref": params.source_ref,
                    "bug_injection_count": params.bug_injection_count,
                    "max_duration_seconds": params.max_duration_seconds,
                }
            ],
            start_to_close_timeout=timedelta(seconds=params.max_duration_seconds + 60),
        )

        return SimulationTrainingResult(
            simulation_id=result.get("simulation_id", ""),
            detection_rate=result.get("detection_rate", 0.0),
            completed=True,
        )
