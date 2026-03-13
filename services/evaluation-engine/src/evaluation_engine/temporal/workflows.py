"""Temporal workflow definitions for the Evaluation Engine."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from evaluation_engine.temporal.activities import run_evaluation


@workflow.defn
class EvaluationWorkflow:
    """Temporal workflow that orchestrates a full evaluation run.

    Delegates to the :func:`run_evaluation` activity which handles
    layer execution, event publishing, and report generation.
    """

    @workflow.run
    async def run(self, task_id: str, sandbox_session_id: str) -> dict:
        """Execute the evaluation pipeline.

        Args:
            task_id: Branded task identifier.
            sandbox_session_id: Active sandbox session to evaluate.

        Returns:
            A dict representation of the :class:`EvaluationReport`.
        """
        result = await workflow.execute_activity(
            run_evaluation,
            args=[task_id, sandbox_session_id],
            start_to_close_timeout=timedelta(minutes=10),
        )
        return result
