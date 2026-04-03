"""Tests for the cross-project knowledge transfer module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from knowledge_memory.knowledge_transfer import (
    find_cross_project_heuristics,
    promote_to_global,
    run_knowledge_transfer,
)
from knowledge_memory.models import HeuristicRule


@pytest.fixture
def mock_engine() -> AsyncMock:
    return AsyncMock()


class TestFindCrossProjectHeuristics:
    @pytest.mark.asyncio
    async def test_finds_common_heuristics(self, mock_engine: AsyncMock) -> None:
        mock_engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="auth",
                condition="token refresh fails",
                action="use mutex",
                project_id="proj-1",
            ),
            HeuristicRule(
                domain="auth",
                condition="token refresh fails",
                action="use mutex",
                project_id="proj-2",
            ),
        ]

        groups = await find_cross_project_heuristics(mock_engine, min_project_count=2)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    @pytest.mark.asyncio
    async def test_ignores_single_project(self, mock_engine: AsyncMock) -> None:
        mock_engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="auth",
                condition="token refresh fails",
                action="use mutex",
                project_id="proj-1",
            ),
        ]

        groups = await find_cross_project_heuristics(mock_engine, min_project_count=2)
        assert len(groups) == 0

    @pytest.mark.asyncio
    async def test_ignores_global_heuristics(self, mock_engine: AsyncMock) -> None:
        mock_engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="auth",
                condition="token refresh fails",
                action="use mutex",
                project_id="",  # Already global
            ),
            HeuristicRule(
                domain="auth",
                condition="token refresh fails",
                action="use mutex",
                project_id="",  # Already global
            ),
        ]

        groups = await find_cross_project_heuristics(mock_engine, min_project_count=2)
        assert len(groups) == 0


class TestPromoteToGlobal:
    @pytest.mark.asyncio
    async def test_promotes_highest_confidence(self, mock_engine: AsyncMock) -> None:
        mock_engine.store_heuristic.return_value = HeuristicRule(
            domain="auth",
            condition="test",
            action="act",
            confidence=0.9,
        )

        group = [
            HeuristicRule(
                domain="auth",
                condition="test",
                action="act",
                confidence=0.7,
                project_id="proj-1",
            ),
            HeuristicRule(
                domain="auth",
                condition="test",
                action="act",
                confidence=0.8,
                project_id="proj-2",
            ),
        ]

        result = await promote_to_global(mock_engine, group)
        assert result is not None
        # The stored heuristic should have been based on the 0.8 confidence entry
        call_args = mock_engine.store_heuristic.call_args[0][0]
        assert call_args.project_id == ""  # Global scope
        assert call_args.confidence == pytest.approx(0.9)  # 0.8 + 0.1 boost

    @pytest.mark.asyncio
    async def test_empty_group(self, mock_engine: AsyncMock) -> None:
        result = await promote_to_global(mock_engine, [])
        assert result is None


class TestRunKnowledgeTransfer:
    @pytest.mark.asyncio
    async def test_end_to_end(self, mock_engine: AsyncMock) -> None:
        mock_engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="db",
                condition="n+1 query detected",
                action="add eager loading",
                project_id="proj-1",
                confidence=0.7,
            ),
            HeuristicRule(
                domain="db",
                condition="n+1 query detected",
                action="add eager loading",
                project_id="proj-2",
                confidence=0.8,
            ),
        ]
        mock_engine.store_heuristic.return_value = HeuristicRule(
            domain="db",
            condition="n+1 query detected",
            action="add eager loading",
            confidence=0.9,
        )

        promoted = await run_knowledge_transfer(mock_engine, min_project_count=2)
        assert promoted == 1
        mock_engine.store_heuristic.assert_called_once()
