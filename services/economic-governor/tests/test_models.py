"""Tests for Economic Governor domain models."""

from __future__ import annotations

import pytest

from architect_common.enums import BudgetPhase, EnforcementLevel
from architect_common.types import AgentId, TaskId
from economic_governor.models import (
    AgentEfficiencyScore,
    BudgetAllocationRequest,
    BudgetAllocationResult,
    BudgetSnapshot,
    EfficiencyLeaderboard,
    EnforcementRecord,
    PhaseAllocation,
    PhaseStatus,
    SpinDetection,
)


class TestModels:
    """Verify domain models are frozen and validate correctly."""

    def test_phase_allocation_frozen(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.TESTING, allocated_tokens=1000)
        with pytest.raises(Exception):  # noqa: B017 (ValidationError on frozen model)
            alloc.allocated_tokens = 2000  # type: ignore[misc]

    def test_budget_snapshot_defaults(self) -> None:
        snap = BudgetSnapshot()
        assert snap.allocated_tokens == 0
        assert snap.consumed_tokens == 0
        assert snap.consumed_pct == 0.0
        assert snap.enforcement_level == EnforcementLevel.NONE
        assert snap.phase_breakdown == []

    def test_phase_status_creation(self) -> None:
        ps = PhaseStatus(
            phase=BudgetPhase.IMPLEMENTATION,
            allocated_tokens=4_000_000,
            allocated_pct=40.0,
            consumed_tokens=1_000_000,
            consumed_pct=25.0,
        )
        assert ps.phase == BudgetPhase.IMPLEMENTATION
        assert ps.consumed_pct == 25.0

    def test_agent_efficiency_score_creation(self) -> None:
        score = AgentEfficiencyScore(
            agent_id=AgentId("agent-test001"),
            efficiency_score=0.85,
            tasks_completed=10,
            tasks_failed=2,
            quality_score=0.9,
            tokens_consumed=50000,
            cost_usd=0.05,
            rank=1,
        )
        assert score.agent_id == "agent-test001"
        assert score.rank == 1

    def test_efficiency_leaderboard(self) -> None:
        board = EfficiencyLeaderboard(
            entries=[
                AgentEfficiencyScore(
                    agent_id=AgentId("agent-a"),
                    efficiency_score=0.9,
                    rank=1,
                ),
                AgentEfficiencyScore(
                    agent_id=AgentId("agent-b"),
                    efficiency_score=0.7,
                    rank=2,
                ),
            ]
        )
        assert len(board.entries) == 2
        assert board.entries[0].rank == 1

    def test_enforcement_record_creation(self) -> None:
        record = EnforcementRecord(
            id="enf-test001",
            level=EnforcementLevel.ALERT,
            action_type="budget_alert",
            budget_consumed_pct=82.5,
        )
        assert record.level == EnforcementLevel.ALERT
        assert record.target_id is None

    def test_spin_detection_creation(self) -> None:
        detection = SpinDetection(
            agent_id=AgentId("agent-spin"),
            task_id=TaskId("task-spin"),
            is_spinning=True,
            retry_count=4,
            tokens_since_last_diff=10000,
        )
        assert detection.is_spinning is True
        assert detection.retry_count == 4

    def test_budget_allocation_request(self) -> None:
        req = BudgetAllocationRequest(
            project_id="proj-001",
            estimated_complexity=0.8,
            priority=3,
        )
        assert req.project_id == "proj-001"
        assert req.estimated_complexity == 0.8

    def test_budget_allocation_result(self) -> None:
        result = BudgetAllocationResult(
            project_id="proj-001",
            total_tokens=5_000_000,
            total_usd=5.0,
            phase_allocations=[
                PhaseAllocation(
                    phase=BudgetPhase.IMPLEMENTATION,
                    allocated_tokens=2_000_000,
                    allocated_pct=40.0,
                ),
            ],
        )
        assert result.total_tokens == 5_000_000
        assert len(result.phase_allocations) == 1
