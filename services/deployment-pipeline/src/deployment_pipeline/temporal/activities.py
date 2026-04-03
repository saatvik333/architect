"""Temporal activity definitions for the Deployment Pipeline.

Activities are defined as methods on :class:`DeploymentActivities` so that the
Temporal worker can inject shared state (e.g. HTTP clients, config, event publisher).
"""

from __future__ import annotations

from typing import Any

import httpx
from temporalio import activity

from architect_common.enums import (
    DeploymentStage,
    EventType,
    RollbackReason,
)
from architect_common.logging import get_logger
from architect_common.types import DeploymentId, TaskId, utcnow
from architect_events.schemas import (
    DeploymentCompletedEvent,
    DeploymentRolledBackEvent,
    DeploymentStageChangedEvent,
    DeploymentStartedEvent,
    EventEnvelope,
)

logger = get_logger(component="deployment_pipeline.temporal.activities")


class DeploymentActivities:
    """Temporal activities that interact with external services for deployment."""

    def __init__(
        self,
        sandbox_base_url: str = "http://localhost:8007",
        evaluation_engine_url: str = "http://localhost:8008",
        human_interface_url: str = "http://localhost:8016",
        event_publisher: Any | None = None,
    ) -> None:
        self._sandbox_url = sandbox_base_url
        self._eval_url = evaluation_engine_url
        self._human_url = human_interface_url
        self._publisher = event_publisher

    async def _publish(self, envelope: EventEnvelope) -> None:
        """Publish an event if the publisher is available."""
        if self._publisher is not None:
            await self._publisher.publish(envelope)

    @activity.defn
    async def deploy_to_staging_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Deploy the artifact to the staging environment.

        Calls the sandbox service to create and start the staging container.
        """
        activity.logger.info("deploy_to_staging_activity started")
        deployment_id = params.get("deployment_id", "unknown")
        artifact = params.get("artifact", {})

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._sandbox_url}/api/v1/sandboxes",
                    json={
                        "image": artifact.get("artifact_ref", ""),
                        "environment": "staging",
                        "labels": {"deployment_id": deployment_id},
                    },
                )
                response.raise_for_status()

            # Publish deployment started event.
            await self._publish(
                EventEnvelope(
                    type=EventType.DEPLOYMENT_STARTED,
                    payload=DeploymentStartedEvent(
                        deployment_id=DeploymentId(deployment_id),
                        task_id=TaskId(artifact.get("task_id", "")),
                        artifact_ref=artifact.get("artifact_ref", ""),
                    ).model_dump(mode="json"),
                )
            )

            return {"success": True, "deployment_id": deployment_id}
        except Exception as exc:
            activity.logger.error(f"Staging deployment failed: {exc}")
            return {"success": False, "error": str(exc)}

    @activity.defn
    async def run_smoke_tests_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run the smoke test suite against the staging deployment.

        Calls the evaluation engine's smoke-test endpoint.
        """
        activity.logger.info("run_smoke_tests_activity started")
        deployment_id = params.get("deployment_id", "unknown")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self._eval_url}/api/v1/smoke-tests",
                    json={"deployment_id": deployment_id},
                )
                response.raise_for_status()
                result = response.json()

            return {
                "passed": result.get("passed", False),
                "tests_run": result.get("tests_run", 0),
                "tests_failed": result.get("tests_failed", 0),
                "failure_details": result.get("failure_details", []),
                "duration_seconds": result.get("duration_seconds", 0.0),
            }
        except Exception as exc:
            activity.logger.error(f"Smoke tests failed: {exc}")
            return {
                "passed": False,
                "tests_run": 0,
                "tests_failed": 0,
                "failure_details": [str(exc)],
                "duration_seconds": 0.0,
            }

    @activity.defn
    async def request_approval_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Request human approval via the Human Interface service."""
        activity.logger.info("request_approval_activity started")
        deployment_id = params.get("deployment_id", "unknown")
        confidence = params.get("confidence", 0.0)
        artifact = params.get("artifact", {})

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._human_url}/api/v1/escalations",
                    json={
                        "title": f"Deployment approval: {artifact.get('artifact_ref', 'unknown')}",
                        "description": (
                            f"Deployment {deployment_id} requires approval. "
                            f"Confidence: {confidence:.2%}. "
                            f"Task: {artifact.get('task_id', 'unknown')}"
                        ),
                        "category": "architectural",
                        "severity": "high",
                    },
                )
                response.raise_for_status()
                result = response.json()

            return {
                "approval_requested": True,
                "escalation_id": result.get("escalation_id", ""),
            }
        except Exception as exc:
            activity.logger.error(f"Failed to request approval: {exc}")
            return {"approval_requested": False, "error": str(exc)}

    @activity.defn
    async def deploy_canary_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Deploy the canary with initial traffic percentage."""
        activity.logger.info("deploy_canary_activity started")
        deployment_id = params.get("deployment_id", "unknown")
        traffic_pct = params.get("traffic_pct", 5)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._sandbox_url}/api/v1/traffic",
                    json={
                        "deployment_id": deployment_id,
                        "traffic_pct": traffic_pct,
                        "mode": "canary",
                    },
                )
                response.raise_for_status()

            return {"success": True, "traffic_pct": traffic_pct}
        except Exception as exc:
            activity.logger.error(f"Canary deployment failed: {exc}")
            return {"success": False, "error": str(exc)}

    @activity.defn
    async def collect_health_metrics_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Collect current health metrics from the deployed service."""
        activity.logger.info("collect_health_metrics_activity started")
        deployment_id = params.get("deployment_id", "unknown")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._sandbox_url}/api/v1/metrics/{deployment_id}",
                )
                response.raise_for_status()
                metrics = response.json()

            return {
                "error_rate": metrics.get("error_rate", 0.0),
                "p50_latency_ms": metrics.get("p50_latency_ms", 0.0),
                "p95_latency_ms": metrics.get("p95_latency_ms", 0.0),
                "p99_latency_ms": metrics.get("p99_latency_ms", 0.0),
                "request_count": metrics.get("request_count", 0),
                "timestamp": utcnow().isoformat(),
            }
        except Exception as exc:
            activity.logger.error(f"Health metric collection failed: {exc}")
            return {
                "error_rate": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "request_count": 0,
                "timestamp": utcnow().isoformat(),
            }

    @activity.defn
    async def collect_baseline_metrics_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Collect baseline metrics from the current production deployment."""
        activity.logger.info("collect_baseline_metrics_activity started")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._sandbox_url}/api/v1/baseline-metrics",
                )
                response.raise_for_status()
                baseline = response.json()

            return {
                "error_rate_mean": baseline.get("error_rate_mean", 0.01),
                "error_rate_stddev": baseline.get("error_rate_stddev", 0.005),
                "p95_latency_ms": baseline.get("p95_latency_ms", 100.0),
            }
        except Exception as exc:
            activity.logger.warning(f"Baseline metric collection failed, using defaults: {exc}")
            return {
                "error_rate_mean": 0.01,
                "error_rate_stddev": 0.005,
                "p95_latency_ms": 100.0,
            }

    @activity.defn
    async def check_rollback_criteria_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate whether the deployment should be rolled back.

        Compares current health metrics against the baseline using
        configurable thresholds for error rate (sigma-based) and latency
        (multiplier-based).
        """
        activity.logger.info("check_rollback_criteria_activity started")
        health = params.get("health", {})
        baseline = params.get("baseline", {})
        error_sigma = params.get("rollback_error_sigma", 2.0)
        latency_multiplier = params.get("rollback_latency_multiplier", 2.0)

        current_error_rate = health.get("error_rate", 0.0)
        baseline_mean = baseline.get("error_rate_mean", 0.01)
        baseline_stddev = baseline.get("error_rate_stddev", 0.005)
        baseline_p95 = baseline.get("p95_latency_ms", 100.0)
        current_p95 = health.get("p95_latency_ms", 0.0)

        # Check error rate: current > mean + (sigma * stddev).
        error_threshold = baseline_mean + (error_sigma * baseline_stddev)
        if current_error_rate > error_threshold:
            return {
                "should_rollback": True,
                "reason": RollbackReason.ERROR_RATE_EXCEEDED,
                "detail": (
                    f"Error rate {current_error_rate:.4f} exceeds threshold "
                    f"{error_threshold:.4f} (mean={baseline_mean:.4f} + "
                    f"{error_sigma}*stddev={baseline_stddev:.4f})"
                ),
            }

        # Check latency: current p95 > baseline p95 * multiplier.
        latency_threshold = baseline_p95 * latency_multiplier
        if current_p95 > latency_threshold:
            return {
                "should_rollback": True,
                "reason": RollbackReason.LATENCY_EXCEEDED,
                "detail": (
                    f"P95 latency {current_p95:.1f}ms exceeds threshold "
                    f"{latency_threshold:.1f}ms (baseline={baseline_p95:.1f}ms * "
                    f"{latency_multiplier})"
                ),
            }

        return {"should_rollback": False}

    @activity.defn
    async def set_traffic_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set the traffic percentage for the new deployment."""
        activity.logger.info("set_traffic_activity started")
        deployment_id = params.get("deployment_id", "unknown")
        traffic_pct = params.get("traffic_pct", 100)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.put(
                    f"{self._sandbox_url}/api/v1/traffic",
                    json={
                        "deployment_id": deployment_id,
                        "traffic_pct": traffic_pct,
                    },
                )
                response.raise_for_status()

            return {"success": True, "traffic_pct": traffic_pct}
        except Exception as exc:
            activity.logger.error(f"Failed to set traffic to {traffic_pct}%: {exc}")
            return {"success": False, "error": str(exc)}

    @activity.defn
    async def rollback_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a rollback: route 100% traffic back to the previous version."""
        activity.logger.info("rollback_activity started")
        deployment_id = params.get("deployment_id", "unknown")
        reason = params.get("reason", "unknown")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._sandbox_url}/api/v1/rollback",
                    json={
                        "deployment_id": deployment_id,
                        "reason": reason,
                    },
                )
                response.raise_for_status()

            return {"success": True, "deployment_id": deployment_id, "reason": reason}
        except Exception as exc:
            activity.logger.error(f"Rollback failed: {exc}")
            return {"success": False, "error": str(exc)}

    @activity.defn
    async def run_acceptance_verification_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run acceptance verification against the fully rolled-out deployment."""
        activity.logger.info("run_acceptance_verification_activity started")
        deployment_id = params.get("deployment_id", "unknown")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self._eval_url}/api/v1/acceptance-verification",
                    json={"deployment_id": deployment_id},
                )
                response.raise_for_status()
                result = response.json()

            return {
                "passed": result.get("passed", False),
                "details": result.get("details", ""),
            }
        except Exception as exc:
            activity.logger.error(f"Acceptance verification failed: {exc}")
            return {"passed": False, "details": str(exc)}

    @activity.defn
    async def publish_deployment_event_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Publish deployment lifecycle events to the event bus."""
        activity.logger.info("publish_deployment_event_activity started")
        event_type = params.get("event_type", "")
        deployment_id = params.get("deployment_id", "unknown")

        try:
            if event_type == "started":
                await self._publish(
                    EventEnvelope(
                        type=EventType.DEPLOYMENT_STARTED,
                        payload=DeploymentStartedEvent(
                            deployment_id=DeploymentId(deployment_id),
                            task_id=TaskId(params.get("task_id", "")),
                            artifact_ref=params.get("artifact_ref", ""),
                        ).model_dump(mode="json"),
                    )
                )
            elif event_type == "stage_changed":
                await self._publish(
                    EventEnvelope(
                        type=EventType.DEPLOYMENT_STAGE_CHANGED,
                        payload=DeploymentStageChangedEvent(
                            deployment_id=DeploymentId(deployment_id),
                            stage=DeploymentStage(params.get("stage", DeploymentStage.STAGING)),
                            traffic_pct=params.get("traffic_pct", 0),
                        ).model_dump(mode="json"),
                    )
                )
            elif event_type == "completed":
                await self._publish(
                    EventEnvelope(
                        type=EventType.DEPLOYMENT_COMPLETED,
                        payload=DeploymentCompletedEvent(
                            deployment_id=DeploymentId(deployment_id),
                            task_id=TaskId(params.get("task_id", "")),
                            duration_seconds=params.get("duration_seconds", 0.0),
                        ).model_dump(mode="json"),
                    )
                )
            elif event_type == "rolled_back":
                await self._publish(
                    EventEnvelope(
                        type=EventType.DEPLOYMENT_ROLLED_BACK,
                        payload=DeploymentRolledBackEvent(
                            deployment_id=DeploymentId(deployment_id),
                            reason=RollbackReason(params.get("reason", RollbackReason.MANUAL)),
                            stage_at_rollback=DeploymentStage(
                                params.get("stage_at_rollback", DeploymentStage.STAGING)
                            ),
                        ).model_dump(mode="json"),
                    )
                )

            return {"published": True, "event_type": event_type}
        except Exception as exc:
            activity.logger.error(f"Failed to publish event: {exc}")
            return {"published": False, "error": str(exc)}
