"""Deployment pipeline orchestration manager."""

from __future__ import annotations

from typing import Any

from temporalio.client import Client, WorkflowHandle

from architect_common.logging import get_logger
from architect_common.types import DeploymentId, new_deployment_id
from deployment_pipeline.config import DeploymentPipelineConfig
from deployment_pipeline.models import (
    DeploymentArtifact,
    DeploymentPlan,
    DeploymentState,
    RolloutStep,
)

logger = get_logger(component="deployment_pipeline.pipeline_manager")


class PipelineManager:
    """Manages deployment lifecycle: creation, status queries, cancellation, rollback.

    Uses Temporal workflows for durable execution while maintaining an
    in-memory cache of deployment state for fast API responses.
    """

    def __init__(
        self,
        config: DeploymentPipelineConfig,
        temporal_client: Client | None = None,
    ) -> None:
        self._config = config
        self._client = temporal_client
        self._deployments: dict[DeploymentId, DeploymentState] = {}

    @property
    def temporal_client(self) -> Client | None:
        return self._client

    @temporal_client.setter
    def temporal_client(self, client: Client) -> None:
        self._client = client

    def _build_plan(
        self,
        deployment_id: DeploymentId,
        artifact: DeploymentArtifact,
    ) -> DeploymentPlan:
        """Create a deployment plan with steps derived from configuration."""
        cfg = self._config
        return DeploymentPlan(
            deployment_id=deployment_id,
            artifact=artifact,
            rollout_steps=[
                RolloutStep(
                    traffic_pct=cfg.canary_traffic_pct,
                    min_duration_seconds=cfg.health_check_duration_seconds,
                    health_check_interval_seconds=cfg.health_check_interval_seconds,
                ),
                RolloutStep(
                    traffic_pct=25,
                    min_duration_seconds=cfg.health_check_duration_seconds,
                    health_check_interval_seconds=cfg.health_check_interval_seconds,
                ),
                RolloutStep(
                    traffic_pct=50,
                    min_duration_seconds=cfg.health_check_duration_seconds,
                    health_check_interval_seconds=cfg.health_check_interval_seconds,
                ),
                RolloutStep(
                    traffic_pct=100,
                    min_duration_seconds=cfg.health_check_duration_seconds,
                    health_check_interval_seconds=cfg.health_check_interval_seconds,
                ),
            ],
            rollback_error_sigma=cfg.rollback_error_sigma,
            rollback_latency_multiplier=cfg.rollback_latency_multiplier,
        )

    async def start_deployment(
        self,
        artifact: DeploymentArtifact,
        eval_report: str = "",
        confidence: float = 0.0,
    ) -> DeploymentState:
        """Validate artifact, create a plan, and start the Temporal workflow.

        Args:
            artifact: The artifact to deploy.
            eval_report: Summary of the evaluation report.
            confidence: Confidence score from the evaluation engine.

        Returns:
            The initial deployment state.

        Raises:
            RuntimeError: If the Temporal client is not connected.
        """
        deployment_id = new_deployment_id()
        plan = self._build_plan(deployment_id, artifact)

        state = DeploymentState(
            deployment_id=deployment_id,
            artifact=artifact,
            confidence=confidence,
        )
        self._deployments[deployment_id] = state

        logger.info(
            "starting deployment",
            deployment_id=deployment_id,
            task_id=artifact.task_id,
            artifact_ref=artifact.artifact_ref,
            confidence=confidence,
        )

        if self._client is not None:
            workflow_params: dict[str, Any] = {
                "plan": plan.model_dump(mode="json"),
                "confidence": confidence,
                "first_deploy_requires_human": self._config.first_deploy_requires_human,
                "auto_approve_threshold": self._config.auto_approve_confidence_threshold,
                "approval_timeout_minutes": self._config.approval_timeout_minutes,
            }

            await self._client.start_workflow(
                "DeploymentWorkflow",
                workflow_params,
                id=f"deployment-{deployment_id}",
                task_queue=self._config.temporal_task_queue,
            )
            logger.info("temporal workflow started", deployment_id=deployment_id)
        else:
            logger.warning(
                "temporal client not available — deployment registered but workflow not started",
                deployment_id=deployment_id,
            )

        return state

    async def get_deployment_status(self, deployment_id: DeploymentId) -> DeploymentState | None:
        """Return the current state of a deployment.

        Checks the in-memory cache first, then queries the Temporal workflow
        if available.
        """
        state = self._deployments.get(deployment_id)
        if state is not None:
            return state

        # Attempt to query the Temporal workflow.
        if self._client is not None:
            try:
                handle: WorkflowHandle[Any, Any] = self._client.get_workflow_handle(
                    f"deployment-{deployment_id}"
                )
                result = await handle.query("get_state")
                if isinstance(result, dict):
                    state = DeploymentState.model_validate(result)
                    self._deployments[deployment_id] = state
                    return state
            except Exception:
                logger.debug(
                    "failed to query temporal workflow",
                    deployment_id=deployment_id,
                    exc_info=True,
                )

        return None

    def list_deployments(
        self,
        status_filter: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[DeploymentState]:
        """List deployments with optional status filtering and pagination."""
        deployments = list(self._deployments.values())

        if status_filter:
            deployments = [d for d in deployments if d.status == status_filter]

        # Sort by start time, newest first.
        deployments.sort(key=lambda d: d.started_at, reverse=True)
        return deployments[offset : offset + limit]

    async def cancel_deployment(self, deployment_id: DeploymentId) -> bool:
        """Cancel an in-progress deployment workflow.

        Returns:
            True if cancellation was requested successfully.
        """
        if self._client is None:
            logger.warning("temporal client not available — cannot cancel")
            return False

        try:
            handle: WorkflowHandle[Any, Any] = self._client.get_workflow_handle(
                f"deployment-{deployment_id}"
            )
            await handle.cancel()
            logger.info("deployment cancellation requested", deployment_id=deployment_id)

            state = self._deployments.get(deployment_id)
            if state is not None:
                state.status = "cancelled"  # type: ignore[assignment]

            return True
        except Exception:
            logger.error(
                "failed to cancel deployment",
                deployment_id=deployment_id,
                exc_info=True,
            )
            return False

    async def trigger_rollback(
        self,
        deployment_id: DeploymentId,
        reason: str = "manual",
    ) -> bool:
        """Signal the deployment workflow to initiate rollback.

        Returns:
            True if the rollback signal was sent successfully.
        """
        if self._client is None:
            logger.warning("temporal client not available — cannot trigger rollback")
            return False

        try:
            handle: WorkflowHandle[Any, Any] = self._client.get_workflow_handle(
                f"deployment-{deployment_id}"
            )
            await handle.signal("rollback_requested", {"reason": reason})
            logger.info(
                "rollback signal sent",
                deployment_id=deployment_id,
                reason=reason,
            )
            return True
        except Exception:
            logger.error(
                "failed to signal rollback",
                deployment_id=deployment_id,
                exc_info=True,
            )
            return False

    def update_state(self, deployment_id: DeploymentId, state: DeploymentState) -> None:
        """Update the cached deployment state (called by activities)."""
        self._deployments[deployment_id] = state
