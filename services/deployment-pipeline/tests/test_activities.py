"""Tests for Deployment Pipeline Temporal activities (mock HTTP calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from architect_common.enums import RollbackReason
from deployment_pipeline.temporal.activities import DeploymentActivities


class TestCheckRollbackCriteria:
    """Tests for check_rollback_criteria_activity — no HTTP, pure logic."""

    @pytest.fixture
    def activities_no_http(self) -> DeploymentActivities:
        """Activities instance (HTTP is not needed for rollback checks)."""
        return DeploymentActivities(event_publisher=AsyncMock())

    async def test_healthy_metrics_no_rollback(
        self, activities_no_http: DeploymentActivities
    ) -> None:
        """Should return no rollback when metrics are within thresholds."""
        result = await activities_no_http.check_rollback_criteria_activity(
            {
                "health": {"error_rate": 0.005, "p95_latency_ms": 80.0},
                "baseline": {
                    "error_rate_mean": 0.01,
                    "error_rate_stddev": 0.005,
                    "p95_latency_ms": 100.0,
                },
                "rollback_error_sigma": 2.0,
                "rollback_latency_multiplier": 2.0,
            }
        )
        assert result["should_rollback"] is False

    async def test_error_rate_exceeded(self, activities_no_http: DeploymentActivities) -> None:
        """Should trigger rollback when error rate exceeds sigma threshold."""
        result = await activities_no_http.check_rollback_criteria_activity(
            {
                "health": {"error_rate": 0.05, "p95_latency_ms": 80.0},
                "baseline": {
                    "error_rate_mean": 0.01,
                    "error_rate_stddev": 0.005,
                    "p95_latency_ms": 100.0,
                },
                "rollback_error_sigma": 2.0,
                "rollback_latency_multiplier": 2.0,
            }
        )
        assert result["should_rollback"] is True
        assert result["reason"] == RollbackReason.ERROR_RATE_EXCEEDED

    async def test_latency_exceeded(self, activities_no_http: DeploymentActivities) -> None:
        """Should trigger rollback when p95 latency exceeds multiplier threshold."""
        result = await activities_no_http.check_rollback_criteria_activity(
            {
                "health": {"error_rate": 0.005, "p95_latency_ms": 250.0},
                "baseline": {
                    "error_rate_mean": 0.01,
                    "error_rate_stddev": 0.005,
                    "p95_latency_ms": 100.0,
                },
                "rollback_error_sigma": 2.0,
                "rollback_latency_multiplier": 2.0,
            }
        )
        assert result["should_rollback"] is True
        assert result["reason"] == RollbackReason.LATENCY_EXCEEDED

    async def test_exact_threshold_no_rollback(
        self, activities_no_http: DeploymentActivities
    ) -> None:
        """Metrics exactly at the threshold should not trigger rollback."""
        result = await activities_no_http.check_rollback_criteria_activity(
            {
                "health": {
                    "error_rate": 0.02,  # mean + 2*stddev = 0.01 + 2*0.005 = 0.02
                    "p95_latency_ms": 200.0,  # baseline * 2 = 200
                },
                "baseline": {
                    "error_rate_mean": 0.01,
                    "error_rate_stddev": 0.005,
                    "p95_latency_ms": 100.0,
                },
                "rollback_error_sigma": 2.0,
                "rollback_latency_multiplier": 2.0,
            }
        )
        assert result["should_rollback"] is False

    async def test_custom_sigma(self, activities_no_http: DeploymentActivities) -> None:
        """Should respect custom sigma value."""
        # With sigma=1.0, threshold = 0.01 + 1.0*0.005 = 0.015
        result = await activities_no_http.check_rollback_criteria_activity(
            {
                "health": {"error_rate": 0.016, "p95_latency_ms": 80.0},
                "baseline": {
                    "error_rate_mean": 0.01,
                    "error_rate_stddev": 0.005,
                    "p95_latency_ms": 100.0,
                },
                "rollback_error_sigma": 1.0,
                "rollback_latency_multiplier": 2.0,
            }
        )
        assert result["should_rollback"] is True


class TestPublishDeploymentEvent:
    """Tests for publish_deployment_event_activity."""

    async def test_publish_started_event(
        self, activities: DeploymentActivities, mock_publisher: AsyncMock
    ) -> None:
        """Should publish a DEPLOYMENT_STARTED event."""
        result = await activities.publish_deployment_event_activity(
            {
                "event_type": "started",
                "deployment_id": "deploy-123",
                "task_id": "task-abc",
                "artifact_ref": "img:v1",
            }
        )
        assert result["published"] is True
        mock_publisher.publish.assert_called_once()
        envelope = mock_publisher.publish.call_args[0][0]
        assert envelope.type == "deployment.started"

    async def test_publish_stage_changed_event(
        self, activities: DeploymentActivities, mock_publisher: AsyncMock
    ) -> None:
        """Should publish a DEPLOYMENT_STAGE_CHANGED event."""
        result = await activities.publish_deployment_event_activity(
            {
                "event_type": "stage_changed",
                "deployment_id": "deploy-123",
                "stage": "canary_5",
                "traffic_pct": 5,
            }
        )
        assert result["published"] is True
        mock_publisher.publish.assert_called_once()

    async def test_publish_completed_event(
        self, activities: DeploymentActivities, mock_publisher: AsyncMock
    ) -> None:
        """Should publish a DEPLOYMENT_COMPLETED event."""
        result = await activities.publish_deployment_event_activity(
            {
                "event_type": "completed",
                "deployment_id": "deploy-123",
                "task_id": "task-abc",
                "duration_seconds": 600.0,
            }
        )
        assert result["published"] is True

    async def test_publish_rolled_back_event(
        self, activities: DeploymentActivities, mock_publisher: AsyncMock
    ) -> None:
        """Should publish a DEPLOYMENT_ROLLED_BACK event."""
        result = await activities.publish_deployment_event_activity(
            {
                "event_type": "rolled_back",
                "deployment_id": "deploy-123",
                "reason": "error_rate_exceeded",
                "stage_at_rollback": "canary_5",
            }
        )
        assert result["published"] is True


class TestDeployToStaging:
    """Tests for deploy_to_staging_activity with mocked HTTP."""

    async def test_staging_success(
        self, activities: DeploymentActivities, mock_publisher: AsyncMock
    ) -> None:
        """Successful staging deployment should return success=True."""
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = lambda: None

        with patch("deployment_pipeline.temporal.activities.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await activities.deploy_to_staging_activity(
                {
                    "deployment_id": "deploy-staging-1",
                    "artifact": {
                        "artifact_ref": "img:v1",
                        "task_id": "task-1",
                    },
                }
            )

        assert result["success"] is True

    async def test_staging_failure(self, activities: DeploymentActivities) -> None:
        """Failed staging deployment should return success=False."""
        with patch("deployment_pipeline.temporal.activities.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await activities.deploy_to_staging_activity(
                {
                    "deployment_id": "deploy-staging-2",
                    "artifact": {"artifact_ref": "img:v2"},
                }
            )

        assert result["success"] is False
        assert "error" in result


class TestRunSmokeTests:
    """Tests for run_smoke_tests_activity with mocked HTTP."""

    async def test_smoke_tests_pass(self, activities: DeploymentActivities) -> None:
        """Passing smoke tests should return passed=True."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {
            "passed": True,
            "tests_run": 15,
            "tests_failed": 0,
            "duration_seconds": 10.5,
        }

        with patch("deployment_pipeline.temporal.activities.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await activities.run_smoke_tests_activity({"deployment_id": "deploy-smoke-1"})

        assert result["passed"] is True
        assert result["tests_run"] == 15

    async def test_smoke_tests_connection_failure(self, activities: DeploymentActivities) -> None:
        """Connection failure should return passed=False."""
        with patch("deployment_pipeline.temporal.activities.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await activities.run_smoke_tests_activity({"deployment_id": "deploy-smoke-2"})

        assert result["passed"] is False
