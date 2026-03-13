"""Tests for the new database repositories.

Uses AsyncMock sessions to validate query construction and method behaviour
without requiring a live database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.enums import EvalVerdict
from architect_common.types import (
    AgentId,
    ProposalId,
    TaskId,
    new_agent_id,
    new_proposal_id,
    new_task_id,
)
from architect_db.models.agent import AgentSession
from architect_db.models.evaluation import EvaluationReport
from architect_db.models.proposal import Proposal
from architect_db.models.sandbox import SandboxAuditLog, SandboxSession
from architect_db.repositories.agent_repo import AgentSessionRepository
from architect_db.repositories.evaluation_repo import EvaluationReportRepository
from architect_db.repositories.proposal_repo import ProposalRepository
from architect_db.repositories.sandbox_repo import SandboxSessionRepository

# ── Helpers ──────────────────────────────────────────────────────


def _mock_session() -> AsyncMock:
    """Create a mock AsyncSession with common methods."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_scalars(items: list) -> MagicMock:
    """Create a mock result with scalars().all() returning items."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.scalar_one_or_none.return_value = items[0] if items else None
    return result_mock


# ── ProposalRepository ───────────────────────────────────────────


class TestProposalRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        proposal = Proposal(id=new_proposal_id(), verdict="pending")
        session.get.return_value = proposal

        repo = ProposalRepository(session)
        result = await repo.get_by_id(ProposalId(proposal.id))

        assert result is proposal
        session.get.assert_called_once_with(Proposal, proposal.id)

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = ProposalRepository(session)
        result = await repo.get_by_id(ProposalId("prop-nonexistent"))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_pending(self) -> None:
        session = _mock_session()
        proposals = [
            Proposal(id=new_proposal_id(), verdict="pending"),
            Proposal(id=new_proposal_id(), verdict="pending"),
        ]
        session.execute.return_value = _mock_scalars(proposals)

        repo = ProposalRepository(session)
        result = await repo.get_pending()

        assert len(result) == 2
        assert all(p.verdict == "pending" for p in result)

    @pytest.mark.asyncio
    async def test_get_by_task(self) -> None:
        session = _mock_session()
        task_id = new_task_id()
        proposals = [Proposal(id=new_proposal_id(), task_id=task_id, verdict="accepted")]
        session.execute.return_value = _mock_scalars(proposals)

        repo = ProposalRepository(session)
        result = await repo.get_by_task(task_id)

        assert len(result) == 1


# ── AgentSessionRepository ──────────────────────────────────────


class TestAgentSessionRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        agent = AgentSession(
            id=new_agent_id(), agent_type="coder", model_tier="tier_2", status="running"
        )
        session.get.return_value = agent

        repo = AgentSessionRepository(session)
        result = await repo.get_by_id(AgentId(agent.id))

        assert result is agent
        session.get.assert_called_once_with(AgentSession, agent.id)

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = AgentSessionRepository(session)
        result = await repo.get_by_id(AgentId("agent-nonexistent"))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_sessions(self) -> None:
        session = _mock_session()
        agents = [
            AgentSession(
                id=new_agent_id(), agent_type="coder", model_tier="tier_2", status="running"
            ),
        ]
        session.execute.return_value = _mock_scalars(agents)

        repo = AgentSessionRepository(session)
        result = await repo.get_active_sessions()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_by_task(self) -> None:
        session = _mock_session()
        task_id = new_task_id()
        agents = [
            AgentSession(
                id=new_agent_id(),
                agent_type="coder",
                model_tier="tier_2",
                status="running",
                current_task=task_id,
            ),
        ]
        session.execute.return_value = _mock_scalars(agents)

        repo = AgentSessionRepository(session)
        result = await repo.get_by_task(task_id)

        assert len(result) == 1


# ── SandboxSessionRepository ────────────────────────────────────


class TestSandboxSessionRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        sandbox = SandboxSession(id="sandbox-001", status="running", timeout_seconds=300)
        session.get.return_value = sandbox

        repo = SandboxSessionRepository(session)
        result = await repo.get_by_id("sandbox-001")

        assert result is sandbox
        session.get.assert_called_once_with(SandboxSession, "sandbox-001")

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = SandboxSessionRepository(session)
        result = await repo.get_by_id("sandbox-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active(self) -> None:
        session = _mock_session()
        sandboxes = [
            SandboxSession(id="sandbox-001", status="running", timeout_seconds=300),
            SandboxSession(id="sandbox-002", status="creating", timeout_seconds=300),
        ]
        session.execute.return_value = _mock_scalars(sandboxes)

        repo = SandboxSessionRepository(session)
        result = await repo.get_active()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_task(self) -> None:
        session = _mock_session()
        task_id = new_task_id()
        sandboxes = [
            SandboxSession(
                id="sandbox-001", task_id=task_id, status="completed", timeout_seconds=300
            ),
        ]
        session.execute.return_value = _mock_scalars(sandboxes)

        repo = SandboxSessionRepository(session)
        result = await repo.get_by_task(task_id)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_audit_log(self) -> None:
        session = _mock_session()
        logs = [
            SandboxAuditLog(id="audit-001", session_id="sandbox-001", command="python -m pytest"),
        ]
        session.execute.return_value = _mock_scalars(logs)

        repo = SandboxSessionRepository(session)
        result = await repo.get_audit_log("sandbox-001")

        assert len(result) == 1
        assert result[0].command == "python -m pytest"


# ── EvaluationReportRepository ──────────────────────────────────


class TestEvaluationReportRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = _mock_session()
        report = EvaluationReport(id="eval-001", task_id=new_task_id(), verdict="pass")
        session.get.return_value = report

        repo = EvaluationReportRepository(session)
        result = await repo.get_by_id("eval-001")

        assert result is report
        session.get.assert_called_once_with(EvaluationReport, "eval-001")

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = _mock_session()
        session.get.return_value = None

        repo = EvaluationReportRepository(session)
        result = await repo.get_by_id("eval-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_task(self) -> None:
        session = _mock_session()
        task_id = new_task_id()
        reports = [
            EvaluationReport(id="eval-001", task_id=task_id, verdict="pass"),
            EvaluationReport(id="eval-002", task_id=task_id, verdict="fail_soft"),
        ]
        session.execute.return_value = _mock_scalars(reports)

        repo = EvaluationReportRepository(session)
        result = await repo.get_by_task(task_id)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_latest_for_task_found(self) -> None:
        session = _mock_session()
        task_id = new_task_id()
        report = EvaluationReport(id="eval-latest", task_id=task_id, verdict="pass")
        session.execute.return_value = _mock_scalars([report])

        repo = EvaluationReportRepository(session)
        result = await repo.get_latest_for_task(task_id)

        assert result is report

    @pytest.mark.asyncio
    async def test_get_latest_for_task_not_found(self) -> None:
        session = _mock_session()
        session.execute.return_value = _mock_scalars([])

        repo = EvaluationReportRepository(session)
        result = await repo.get_latest_for_task(TaskId("task-empty"))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_verdict(self) -> None:
        session = _mock_session()
        reports = [
            EvaluationReport(id="eval-001", task_id=new_task_id(), verdict="pass"),
        ]
        session.execute.return_value = _mock_scalars(reports)

        repo = EvaluationReportRepository(session)
        result = await repo.get_by_verdict(EvalVerdict.PASS)

        assert len(result) == 1
