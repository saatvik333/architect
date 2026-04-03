"""Tests for Failure Taxonomy event handlers."""

from __future__ import annotations

import os

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from architect_common.enums import EvalVerdict, EventType, FailureCode
from architect_events.schemas import EventEnvelope
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.config import FailureTaxonomyConfig
from failure_taxonomy.event_handlers import FailureTaxonomyEventHandlers


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock) -> MagicMock:
    """Return a mock session factory."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.fixture
def handlers(
    mock_publisher: AsyncMock, mock_session_factory: MagicMock
) -> FailureTaxonomyEventHandlers:
    """Return event handlers with mocked dependencies."""
    config = FailureTaxonomyConfig(use_llm_classification=False)
    classifier = FailureClassifier(config, llm_client=None)
    return FailureTaxonomyEventHandlers(
        config=config,
        classifier=classifier,
        event_publisher=mock_publisher,
        session_factory=mock_session_factory,
    )


class TestHandleEvaluationCompleted:
    """Test handling of evaluation completion events."""

    async def test_ignores_passing_verdict(self, handlers: FailureTaxonomyEventHandlers) -> None:
        """PASS verdict should be ignored."""
        event = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "task_id": "task-1",
                "verdict": EvalVerdict.PASS,
                "layer_results": [],
            },
        )
        with patch("failure_taxonomy.event_handlers.FailureRecordRepository") as mock_repo_cls:
            await handlers.handle_eval_completed(event)
            mock_repo_cls.assert_not_called()

    async def test_classifies_hard_failure(
        self, handlers: FailureTaxonomyEventHandlers, mock_publisher: AsyncMock
    ) -> None:
        """FAIL_HARD verdict should trigger classification."""
        event = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "task_id": "task-2",
                "verdict": EvalVerdict.FAIL_HARD,
                "layer_results": [
                    {
                        "layer": "compilation",
                        "verdict": "fail_hard",
                        "message": "SyntaxError: invalid syntax",
                    }
                ],
            },
        )
        with patch("failure_taxonomy.event_handlers.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await handlers.handle_eval_completed(event)

            mock_repo.create.assert_called_once()
            mock_publisher.publish.assert_called_once()

    async def test_classifies_soft_failure(
        self, handlers: FailureTaxonomyEventHandlers, mock_publisher: AsyncMock
    ) -> None:
        """FAIL_SOFT verdict should also trigger classification."""
        event = EventEnvelope(
            type=EventType.EVAL_COMPLETED,
            payload={
                "task_id": "task-3",
                "verdict": EvalVerdict.FAIL_SOFT,
                "layer_results": [
                    {
                        "layer": "unit_tests",
                        "verdict": "fail_soft",
                        "message": "2 tests failed",
                    }
                ],
            },
        )
        with patch("failure_taxonomy.event_handlers.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await handlers.handle_eval_completed(event)

            mock_repo.create.assert_called_once()


class TestHandleTaskFailed:
    """Test TASK_FAILED event handling."""

    async def test_classifies_task_failure(
        self, handlers: FailureTaxonomyEventHandlers, mock_publisher: AsyncMock
    ) -> None:
        """Task failures should be classified and persisted."""
        event = EventEnvelope(
            type=EventType.TASK_FAILED,
            payload={
                "task_id": "task-4",
                "agent_id": "agent-1",
                "error_message": "ImportError: No module named 'nonexistent'",
            },
        )
        with patch("failure_taxonomy.event_handlers.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await handlers.handle_task_failed(event)

            mock_repo.create.assert_called_once()
            mock_publisher.publish.assert_called_once()


class TestHandleDeploymentRolledBack:
    """Test DEPLOYMENT_ROLLED_BACK event handling."""

    async def test_classifies_rollback(
        self, handlers: FailureTaxonomyEventHandlers, mock_publisher: AsyncMock
    ) -> None:
        """Deployment rollbacks should be classified."""
        event = EventEnvelope(
            type=EventType.DEPLOYMENT_ROLLED_BACK,
            payload={
                "deployment_id": "deploy-1",
                "reason": "error_rate_exceeded",
                "stage_at_rollback": "canary_5",
            },
        )
        with patch("failure_taxonomy.event_handlers.FailureRecordRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await handlers.handle_deployment_rolled_back(event)

            mock_repo.create.assert_called_once()


class TestSeverityMapping:
    """Test failure code to severity mapping."""

    def test_security_is_critical(self) -> None:
        result = FailureTaxonomyEventHandlers._severity_for_code(FailureCode.F9_SECURITY_VULN)
        assert result == "critical"

    def test_architecture_is_high(self) -> None:
        result = FailureTaxonomyEventHandlers._severity_for_code(FailureCode.F2_ARCHITECTURE_ERROR)
        assert result == "high"

    def test_hallucination_is_high(self) -> None:
        result = FailureTaxonomyEventHandlers._severity_for_code(FailureCode.F3_HALLUCINATION)
        assert result == "high"

    def test_ux_is_low(self) -> None:
        result = FailureTaxonomyEventHandlers._severity_for_code(FailureCode.F7_UX_REJECTION)
        assert result == "low"

    def test_logic_bug_is_medium(self) -> None:
        result = FailureTaxonomyEventHandlers._severity_for_code(FailureCode.F6_LOGIC_BUG)
        assert result == "medium"
