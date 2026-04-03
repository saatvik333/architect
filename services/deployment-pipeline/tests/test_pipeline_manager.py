"""Tests for the PipelineManager."""

from __future__ import annotations

from unittest.mock import AsyncMock

from architect_common.enums import DeploymentStatus
from architect_common.types import DeploymentId, TaskId, new_deployment_id
from deployment_pipeline.models import DeploymentArtifact
from deployment_pipeline.pipeline_manager import PipelineManager


class TestPipelineManager:
    """Unit tests for the PipelineManager."""

    async def test_start_deployment_with_temporal(
        self,
        pipeline_manager: PipelineManager,
        mock_temporal_client: AsyncMock,
    ) -> None:
        """start_deployment should create state and start a Temporal workflow."""
        artifact = DeploymentArtifact(
            task_id=TaskId("task-123"),
            artifact_ref="registry/app:v1.0.0",
            eval_report_summary="All layers passed.",
        )

        state = await pipeline_manager.start_deployment(
            artifact=artifact,
            eval_report="All layers passed.",
            confidence=0.98,
        )

        assert state.status == DeploymentStatus.PENDING
        assert state.artifact is not None
        assert state.artifact.task_id == "task-123"
        assert state.confidence == 0.98
        mock_temporal_client.start_workflow.assert_called_once()

    async def test_start_deployment_without_temporal(
        self,
        pipeline_manager_no_temporal: PipelineManager,
    ) -> None:
        """start_deployment without Temporal should still register the deployment."""
        artifact = DeploymentArtifact(
            task_id=TaskId("task-456"),
            artifact_ref="registry/app:v2.0.0",
        )

        state = await pipeline_manager_no_temporal.start_deployment(
            artifact=artifact,
            confidence=0.5,
        )

        assert state.status == DeploymentStatus.PENDING
        assert state.deployment_id != ""

    async def test_get_deployment_status_cached(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        """get_deployment_status should return from in-memory cache."""
        artifact = DeploymentArtifact(
            task_id=TaskId("task-789"),
            artifact_ref="registry/app:v3.0.0",
        )
        created = await pipeline_manager.start_deployment(artifact=artifact)

        retrieved = await pipeline_manager.get_deployment_status(created.deployment_id)
        assert retrieved is not None
        assert retrieved.deployment_id == created.deployment_id

    async def test_get_deployment_status_not_found(
        self,
        pipeline_manager_no_temporal: PipelineManager,
    ) -> None:
        """get_deployment_status should return None for unknown IDs."""
        result = await pipeline_manager_no_temporal.get_deployment_status(
            DeploymentId("deploy-nonexistent")
        )
        assert result is None

    async def test_list_deployments_empty(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        """list_deployments should return an empty list when no deployments exist."""
        result = pipeline_manager.list_deployments()
        assert result == []

    async def test_list_deployments_with_items(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        """list_deployments should return all tracked deployments."""
        for i in range(3):
            artifact = DeploymentArtifact(
                task_id=TaskId(f"task-{i}"),
                artifact_ref=f"registry/app:v{i}",
            )
            await pipeline_manager.start_deployment(artifact=artifact)

        result = pipeline_manager.list_deployments()
        assert len(result) == 3

    async def test_list_deployments_pagination(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        """list_deployments should respect offset and limit."""
        for i in range(5):
            artifact = DeploymentArtifact(
                task_id=TaskId(f"task-{i}"),
                artifact_ref=f"registry/app:v{i}",
            )
            await pipeline_manager.start_deployment(artifact=artifact)

        page = pipeline_manager.list_deployments(offset=1, limit=2)
        assert len(page) == 2

    async def test_cancel_deployment(
        self,
        pipeline_manager: PipelineManager,
        mock_temporal_client: AsyncMock,
    ) -> None:
        """cancel_deployment should call cancel on the workflow handle."""
        handle = AsyncMock()
        mock_temporal_client.get_workflow_handle.return_value = handle

        artifact = DeploymentArtifact(
            task_id=TaskId("task-cancel"),
            artifact_ref="registry/app:v1",
        )
        state = await pipeline_manager.start_deployment(artifact=artifact)

        result = await pipeline_manager.cancel_deployment(state.deployment_id)
        assert result is True
        handle.cancel.assert_called_once()

    async def test_cancel_without_temporal(
        self,
        pipeline_manager_no_temporal: PipelineManager,
    ) -> None:
        """cancel_deployment without Temporal should return False."""
        result = await pipeline_manager_no_temporal.cancel_deployment(DeploymentId("deploy-xxx"))
        assert result is False

    async def test_trigger_rollback(
        self,
        pipeline_manager: PipelineManager,
        mock_temporal_client: AsyncMock,
    ) -> None:
        """trigger_rollback should signal the workflow."""
        handle = AsyncMock()
        mock_temporal_client.get_workflow_handle.return_value = handle

        artifact = DeploymentArtifact(
            task_id=TaskId("task-rollback"),
            artifact_ref="registry/app:v1",
        )
        state = await pipeline_manager.start_deployment(artifact=artifact)

        result = await pipeline_manager.trigger_rollback(state.deployment_id, reason="manual")
        assert result is True
        handle.signal.assert_called_once_with("rollback_requested", {"reason": "manual"})

    async def test_trigger_rollback_without_temporal(
        self,
        pipeline_manager_no_temporal: PipelineManager,
    ) -> None:
        """trigger_rollback without Temporal should return False."""
        result = await pipeline_manager_no_temporal.trigger_rollback(
            DeploymentId("deploy-xxx"), reason="manual"
        )
        assert result is False

    async def test_update_state(
        self,
        pipeline_manager: PipelineManager,
    ) -> None:
        """update_state should replace the cached deployment state."""
        from deployment_pipeline.models import DeploymentState

        dep_id = new_deployment_id()
        state = DeploymentState(
            deployment_id=dep_id,
            status=DeploymentStatus.CANARY,
            current_traffic_pct=5,
        )
        pipeline_manager.update_state(dep_id, state)

        retrieved = await pipeline_manager.get_deployment_status(dep_id)
        assert retrieved is not None
        assert retrieved.status == DeploymentStatus.CANARY
