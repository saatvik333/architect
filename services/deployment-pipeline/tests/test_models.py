"""Tests for Deployment Pipeline domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from architect_common.enums import DeploymentStage, DeploymentStatus, RollbackReason
from architect_common.types import TaskId, new_deployment_id
from deployment_pipeline.models import (
    BaselineMetrics,
    DeploymentArtifact,
    DeploymentPlan,
    DeploymentState,
    HealthMetrics,
    RolloutStep,
    SmokeTestResult,
)


class TestDeploymentArtifact:
    """Tests for the DeploymentArtifact model."""

    def test_create_artifact(self) -> None:
        """Should create a valid artifact."""
        artifact = DeploymentArtifact(
            task_id=TaskId("task-abc123"),
            artifact_ref="registry.example.com/app:v1.2.3",
            eval_report_summary="All 7 layers passed.",
        )
        assert artifact.task_id == "task-abc123"
        assert artifact.artifact_ref == "registry.example.com/app:v1.2.3"

    def test_artifact_is_frozen(self) -> None:
        """Artifact should be immutable."""
        artifact = DeploymentArtifact(
            task_id=TaskId("task-abc"),
            artifact_ref="img:latest",
        )
        with pytest.raises(ValidationError):
            artifact.artifact_ref = "img:v2"  # type: ignore[misc]


class TestHealthMetrics:
    """Tests for the HealthMetrics model."""

    def test_create_health_metrics(self) -> None:
        """Should create valid health metrics."""
        metrics = HealthMetrics(
            error_rate=0.01,
            p50_latency_ms=10.0,
            p95_latency_ms=50.0,
            p99_latency_ms=100.0,
            request_count=1000,
        )
        assert metrics.error_rate == 0.01
        assert metrics.request_count == 1000

    def test_negative_error_rate_rejected(self) -> None:
        """Negative error rate should be rejected."""
        with pytest.raises(ValidationError):
            HealthMetrics(
                error_rate=-0.1,
                p50_latency_ms=10.0,
                p95_latency_ms=50.0,
                p99_latency_ms=100.0,
                request_count=1000,
            )


class TestBaselineMetrics:
    """Tests for the BaselineMetrics model."""

    def test_create_baseline(self) -> None:
        """Should create valid baseline metrics."""
        baseline = BaselineMetrics(
            error_rate_mean=0.01,
            error_rate_stddev=0.005,
            p95_latency_ms=100.0,
        )
        assert baseline.error_rate_mean == 0.01


class TestRolloutStep:
    """Tests for the RolloutStep model."""

    def test_create_step(self) -> None:
        """Should create a valid rollout step."""
        step = RolloutStep(
            traffic_pct=25,
            min_duration_seconds=300,
            health_check_interval_seconds=30,
        )
        assert step.traffic_pct == 25

    def test_invalid_traffic_pct(self) -> None:
        """Traffic percentage outside 1-100 should be rejected."""
        with pytest.raises(ValidationError):
            RolloutStep(traffic_pct=0, min_duration_seconds=300)

        with pytest.raises(ValidationError):
            RolloutStep(traffic_pct=101, min_duration_seconds=300)


class TestSmokeTestResult:
    """Tests for the SmokeTestResult model."""

    def test_passing_result(self) -> None:
        """Should create a passing smoke test result."""
        result = SmokeTestResult(
            passed=True,
            tests_run=42,
            tests_failed=0,
            duration_seconds=12.5,
        )
        assert result.passed is True
        assert result.tests_failed == 0

    def test_failing_result_with_details(self) -> None:
        """Should include failure details."""
        result = SmokeTestResult(
            passed=False,
            tests_run=42,
            tests_failed=3,
            failure_details=["test_auth_flow", "test_data_write", "test_webhook"],
            duration_seconds=15.0,
        )
        assert result.passed is False
        assert len(result.failure_details) == 3


class TestDeploymentPlan:
    """Tests for the DeploymentPlan model."""

    def test_default_rollout_steps(self) -> None:
        """Default plan should have 4 rollout steps: 5, 25, 50, 100."""
        plan = DeploymentPlan(
            deployment_id=new_deployment_id(),
            artifact=DeploymentArtifact(
                task_id=TaskId("task-1"),
                artifact_ref="img:v1",
            ),
        )
        assert len(plan.rollout_steps) == 4
        expected_pcts = [5, 25, 50, 100]
        actual_pcts = [s.traffic_pct for s in plan.rollout_steps]
        assert actual_pcts == expected_pcts

    def test_custom_rollout_steps(self) -> None:
        """Should accept custom rollout steps."""
        plan = DeploymentPlan(
            deployment_id=new_deployment_id(),
            artifact=DeploymentArtifact(
                task_id=TaskId("task-1"),
                artifact_ref="img:v1",
            ),
            rollout_steps=[
                RolloutStep(traffic_pct=10, min_duration_seconds=60),
                RolloutStep(traffic_pct=100, min_duration_seconds=120),
            ],
        )
        assert len(plan.rollout_steps) == 2


class TestDeploymentState:
    """Tests for the mutable DeploymentState model."""

    def test_initial_state(self) -> None:
        """New state should have pending status."""
        state = DeploymentState(deployment_id=new_deployment_id())
        assert state.status == DeploymentStatus.PENDING
        assert state.current_traffic_pct == 0
        assert state.health_history == []

    def test_state_is_mutable(self) -> None:
        """DeploymentState should allow mutations."""
        state = DeploymentState(deployment_id=new_deployment_id())
        state.status = DeploymentStatus.CANARY
        state.current_traffic_pct = 5
        state.current_stage = DeploymentStage.CANARY_5
        assert state.status == DeploymentStatus.CANARY
        assert state.current_traffic_pct == 5

    def test_rollback_state(self) -> None:
        """Should track rollback reason."""
        state = DeploymentState(deployment_id=new_deployment_id())
        state.status = DeploymentStatus.ROLLED_BACK
        state.rollback_reason = RollbackReason.ERROR_RATE_EXCEEDED
        assert state.rollback_reason == RollbackReason.ERROR_RATE_EXCEEDED
