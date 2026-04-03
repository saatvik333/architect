"""Temporal workflow definitions for the Deployment Pipeline.

The main :class:`DeploymentWorkflow` orchestrates an 8-step deployment:

1. Deploy to staging
2. Run smoke tests (rollback on failure)
3. Approval gate (if first deploy or low confidence)
4. Deploy canary (initial traffic %)
5. Health monitoring loop (collect metrics, check rollback criteria)
6. Progressive rollout (25 -> 50 -> 100%), health check at each step
7. Run acceptance verification
8. Publish deployment completed event
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from architect_common.enums import DeploymentStage, DeploymentStatus, RollbackReason


TASK_QUEUE = "deployment-pipeline"

# Activity name constants — correspond to methods on
# ``deployment_pipeline.temporal.activities.DeploymentActivities``.
ACT_DEPLOY_TO_STAGING = "deploy_to_staging_activity"
ACT_RUN_SMOKE_TESTS = "run_smoke_tests_activity"
ACT_REQUEST_APPROVAL = "request_approval_activity"
ACT_DEPLOY_CANARY = "deploy_canary_activity"
ACT_COLLECT_HEALTH_METRICS = "collect_health_metrics_activity"
ACT_COLLECT_BASELINE_METRICS = "collect_baseline_metrics_activity"
ACT_CHECK_ROLLBACK_CRITERIA = "check_rollback_criteria_activity"
ACT_SET_TRAFFIC = "set_traffic_activity"
ACT_ROLLBACK = "rollback_activity"
ACT_RUN_ACCEPTANCE_VERIFICATION = "run_acceptance_verification_activity"
ACT_PUBLISH_DEPLOYMENT_EVENT = "publish_deployment_event_activity"

# Traffic percentage to stage mapping.
_TRAFFIC_TO_STAGE: dict[int, DeploymentStage] = {
    5: DeploymentStage.CANARY_5,
    25: DeploymentStage.ROLLOUT_25,
    50: DeploymentStage.ROLLOUT_50,
    100: DeploymentStage.ROLLOUT_100,
}


@dataclass
class DeploymentWorkflowParams:
    """Input parameters for the deployment workflow."""

    plan: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    first_deploy_requires_human: bool = True
    auto_approve_threshold: float = 0.95
    approval_timeout_minutes: int = 60


@dataclass
class DeploymentWorkflowResult:
    """Output of the deployment workflow."""

    deployment_id: str = ""
    status: str = "pending"
    rollback_reason: str | None = None
    stages_completed: list[str] = field(default_factory=list)


def _resolve_stage(traffic_pct: int) -> str:
    """Map a traffic percentage to the closest deployment stage."""
    if traffic_pct <= 5:
        return DeploymentStage.CANARY_5
    if traffic_pct <= 25:
        return DeploymentStage.ROLLOUT_25
    if traffic_pct <= 50:
        return DeploymentStage.ROLLOUT_50
    return DeploymentStage.ROLLOUT_100


@workflow.defn
class DeploymentWorkflow:
    """Orchestrates the full deployment pipeline with progressive rollout.

    Supports signals for manual approval and manual rollback.
    """

    def __init__(self) -> None:
        self._approval_received = False
        self._approval_decision: str = "pending"  # "approved" | "denied"
        self._rollback_requested = False
        self._rollback_reason: str = ""
        self._current_status: str = DeploymentStatus.PENDING
        self._current_stage: str | None = None
        self._current_traffic_pct: int = 0
        self._stages_completed: list[str] = []

    @workflow.signal
    async def approval_received(self, data: dict[str, Any]) -> None:
        """Signal: human approval or denial received."""
        self._approval_received = True
        self._approval_decision = data.get("decision", "approved")

    @workflow.signal
    async def rollback_requested(self, data: dict[str, Any]) -> None:
        """Signal: manual rollback requested."""
        self._rollback_requested = True
        self._rollback_reason = data.get("reason", RollbackReason.MANUAL)

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        """Query handler: return current deployment state."""
        return {
            "status": self._current_status,
            "current_stage": self._current_stage,
            "current_traffic_pct": self._current_traffic_pct,
            "stages_completed": self._stages_completed,
        }

    @workflow.run
    async def run(
        self, params: DeploymentWorkflowParams | dict[str, Any]
    ) -> DeploymentWorkflowResult:
        """Execute the 8-step deployment pipeline."""
        if isinstance(params, dict):
            params = DeploymentWorkflowParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in DeploymentWorkflowParams.__dataclass_fields__
                }
            )

        plan = params.plan
        deployment_id = plan.get("deployment_id", "unknown")
        rollout_steps: list[dict[str, Any]] = plan.get("rollout_steps", [])
        artifact = plan.get("artifact", {})

        self._current_status = DeploymentStatus.PENDING

        # ── Step 1: Deploy to staging ────────────────────────────────
        self._current_status = DeploymentStatus.STAGING
        self._current_stage = DeploymentStage.STAGING

        staging_result: dict[str, Any] = await workflow.execute_activity(
            ACT_DEPLOY_TO_STAGING,
            args=[{"deployment_id": deployment_id, "artifact": artifact}],
            start_to_close_timeout=timedelta(minutes=10),
        )

        if not staging_result.get("success", False):
            return await self._do_rollback(
                deployment_id, RollbackReason.SMOKE_TEST_FAILED, "staging deployment failed"
            )

        self._stages_completed.append(DeploymentStage.STAGING)

        # ── Step 2: Run smoke tests ──────────────────────────────────
        self._current_status = DeploymentStatus.SMOKE_TESTING

        smoke_result: dict[str, Any] = await workflow.execute_activity(
            ACT_RUN_SMOKE_TESTS,
            args=[{"deployment_id": deployment_id}],
            start_to_close_timeout=timedelta(minutes=15),
        )

        if not smoke_result.get("passed", False):
            return await self._do_rollback(
                deployment_id, RollbackReason.SMOKE_TEST_FAILED, "smoke tests failed"
            )

        # ── Step 3: Approval gate (conditional) ─────────────────────
        needs_approval = (
            params.first_deploy_requires_human or params.confidence < params.auto_approve_threshold
        )

        if needs_approval:
            self._current_status = DeploymentStatus.AWAITING_APPROVAL

            await workflow.execute_activity(
                ACT_REQUEST_APPROVAL,
                args=[
                    {
                        "deployment_id": deployment_id,
                        "confidence": params.confidence,
                        "artifact": artifact,
                    }
                ],
                start_to_close_timeout=timedelta(minutes=5),
            )

            # Wait for the approval signal.
            try:
                await workflow.wait_condition(
                    lambda: self._approval_received or self._rollback_requested,
                    timeout=timedelta(minutes=params.approval_timeout_minutes),
                )
            except TimeoutError:
                return await self._do_rollback(
                    deployment_id, RollbackReason.APPROVAL_DENIED, "approval timed out"
                )

            if self._rollback_requested:
                return await self._do_rollback(
                    deployment_id,
                    self._rollback_reason or RollbackReason.MANUAL,
                    "rollback requested during approval",
                )

            if self._approval_decision == "denied":
                return await self._do_rollback(
                    deployment_id, RollbackReason.APPROVAL_DENIED, "approval denied"
                )

        # ── Step 4: Collect baseline metrics ─────────────────────────
        baseline: dict[str, Any] = await workflow.execute_activity(
            ACT_COLLECT_BASELINE_METRICS,
            args=[{"deployment_id": deployment_id}],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # ── Steps 5-6: Progressive rollout with health monitoring ────
        for step in rollout_steps:
            if self._rollback_requested:
                return await self._do_rollback(
                    deployment_id,
                    self._rollback_reason or RollbackReason.MANUAL,
                    "rollback requested during rollout",
                )

            traffic_pct = step.get("traffic_pct", 100)
            min_duration = step.get("min_duration_seconds", 300)
            check_interval = step.get("health_check_interval_seconds", 30)
            stage = _resolve_stage(traffic_pct)

            self._current_stage = stage
            self._current_traffic_pct = traffic_pct

            if traffic_pct <= 5:
                # Canary step — use deploy_canary_activity.
                self._current_status = DeploymentStatus.CANARY

                await workflow.execute_activity(
                    ACT_DEPLOY_CANARY,
                    args=[{"deployment_id": deployment_id, "traffic_pct": traffic_pct}],
                    start_to_close_timeout=timedelta(minutes=5),
                )
            else:
                # Progressive rollout step — use set_traffic_activity.
                self._current_status = DeploymentStatus.ROLLING_OUT

                await workflow.execute_activity(
                    ACT_SET_TRAFFIC,
                    args=[{"deployment_id": deployment_id, "traffic_pct": traffic_pct}],
                    start_to_close_timeout=timedelta(minutes=5),
                )

            # Publish stage change event.
            await workflow.execute_activity(
                ACT_PUBLISH_DEPLOYMENT_EVENT,
                args=[
                    {
                        "event_type": "stage_changed",
                        "deployment_id": deployment_id,
                        "stage": stage,
                        "traffic_pct": traffic_pct,
                    }
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Health monitoring loop for this step.
            elapsed = 0
            while elapsed < min_duration:
                if self._rollback_requested:
                    return await self._do_rollback(
                        deployment_id,
                        self._rollback_reason or RollbackReason.MANUAL,
                        "rollback requested during health monitoring",
                    )

                await workflow.sleep(timedelta(seconds=check_interval))
                elapsed += check_interval

                # Collect health metrics.
                health: dict[str, Any] = await workflow.execute_activity(
                    ACT_COLLECT_HEALTH_METRICS,
                    args=[{"deployment_id": deployment_id}],
                    start_to_close_timeout=timedelta(minutes=2),
                )

                # Check rollback criteria.
                rollback_check: dict[str, Any] = await workflow.execute_activity(
                    ACT_CHECK_ROLLBACK_CRITERIA,
                    args=[
                        {
                            "deployment_id": deployment_id,
                            "health": health,
                            "baseline": baseline,
                            "rollback_error_sigma": plan.get("rollback_error_sigma", 2.0),
                            "rollback_latency_multiplier": plan.get(
                                "rollback_latency_multiplier", 2.0
                            ),
                        }
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                if rollback_check.get("should_rollback", False):
                    reason = rollback_check.get("reason", RollbackReason.ERROR_RATE_EXCEEDED)
                    return await self._do_rollback(
                        deployment_id,
                        reason,
                        rollback_check.get("detail", "health check failed"),
                    )

            self._stages_completed.append(stage)

        # ── Step 7: Run acceptance verification ──────────────────────
        self._current_status = DeploymentStatus.VERIFYING

        verification: dict[str, Any] = await workflow.execute_activity(
            ACT_RUN_ACCEPTANCE_VERIFICATION,
            args=[{"deployment_id": deployment_id}],
            start_to_close_timeout=timedelta(minutes=15),
        )

        if not verification.get("passed", False):
            return await self._do_rollback(
                deployment_id,
                RollbackReason.VERIFICATION_FAILED,
                "acceptance verification failed",
            )

        # ── Step 8: Publish completion event ─────────────────────────
        self._current_status = DeploymentStatus.COMPLETED

        await workflow.execute_activity(
            ACT_PUBLISH_DEPLOYMENT_EVENT,
            args=[
                {
                    "event_type": "completed",
                    "deployment_id": deployment_id,
                    "task_id": artifact.get("task_id", ""),
                }
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return DeploymentWorkflowResult(
            deployment_id=deployment_id,
            status=DeploymentStatus.COMPLETED,
            stages_completed=list(self._stages_completed),
        )

    async def _do_rollback(
        self,
        deployment_id: str,
        reason: str,
        detail: str,
    ) -> DeploymentWorkflowResult:
        """Execute the rollback activity and publish the rollback event."""
        workflow.logger.warning(
            f"Rolling back deployment {deployment_id}: {detail} (reason={reason})"
        )
        self._current_status = DeploymentStatus.ROLLED_BACK

        await workflow.execute_activity(
            ACT_ROLLBACK,
            args=[{"deployment_id": deployment_id, "reason": reason}],
            start_to_close_timeout=timedelta(minutes=10),
        )

        await workflow.execute_activity(
            ACT_PUBLISH_DEPLOYMENT_EVENT,
            args=[
                {
                    "event_type": "rolled_back",
                    "deployment_id": deployment_id,
                    "reason": reason,
                    "stage_at_rollback": self._current_stage or DeploymentStage.STAGING,
                }
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return DeploymentWorkflowResult(
            deployment_id=deployment_id,
            status=DeploymentStatus.ROLLED_BACK,
            rollback_reason=reason,
            stages_completed=list(self._stages_completed),
        )
