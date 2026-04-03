"""Tests for the failure analyzer module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from knowledge_memory.failure_analyzer import (
    classify_failure,
    record_heuristic_failure,
    review_heuristic_effectiveness,
)
from knowledge_memory.models import HeuristicRule


class TestClassifyFailure:
    def test_compilation_error(self) -> None:
        assert classify_failure("SyntaxError: unexpected indent") == "compilation"

    def test_import_error(self) -> None:
        assert classify_failure("ModuleNotFoundError: No module named 'foo'") == "import_error"

    def test_test_failure(self) -> None:
        assert classify_failure("AssertionError: expected 5 but got 3") == "test_failure"

    def test_timeout(self) -> None:
        assert classify_failure("TimeoutError: operation timed out") == "timeout"

    def test_resource_exhaustion(self) -> None:
        assert classify_failure("MemoryError: unable to allocate") == "resource_exhaustion"

    def test_security_violation(self) -> None:
        assert classify_failure("SecurityError: permission denied") == "security_violation"

    def test_dependency_error(self) -> None:
        assert (
            classify_failure("dependency resolution failed: version conflict") == "dependency_error"
        )

    def test_runtime_error(self) -> None:
        assert classify_failure("TypeError: unsupported operand type") == "runtime_error"

    def test_unknown(self) -> None:
        assert classify_failure("something completely unexpected") == "unknown"

    def test_case_insensitive(self) -> None:
        assert classify_failure("syntaxerror: bad input") == "compilation"


class TestRecordHeuristicFailure:
    @pytest.mark.asyncio
    async def test_downgrades_heuristics(self) -> None:
        engine = AsyncMock()
        evolved = HeuristicRule(
            domain="test",
            condition="if X",
            action="do Y",
            active=True,
            confidence=0.3,
        )
        engine.evolve_heuristic.return_value = evolved

        deactivated = await record_heuristic_failure(engine, ["h-1", "h-2"])
        assert deactivated == []
        assert engine.evolve_heuristic.call_count == 2

    @pytest.mark.asyncio
    async def test_deactivates_when_inactive(self) -> None:
        engine = AsyncMock()
        evolved = HeuristicRule(
            domain="test",
            condition="if X",
            action="do Y",
            active=False,
            confidence=0.1,
        )
        engine.evolve_heuristic.return_value = evolved

        deactivated = await record_heuristic_failure(engine, ["h-1"])
        assert deactivated == ["h-1"]


class TestReviewHeuristicEffectiveness:
    @pytest.mark.asyncio
    async def test_finds_ineffective(self) -> None:
        engine = AsyncMock()
        engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="test",
                condition="cond",
                action="act",
                success_count=2,
                failure_count=8,
            ),
            HeuristicRule(
                domain="test",
                condition="cond2",
                action="act2",
                success_count=9,
                failure_count=1,
            ),
        ]

        result = await review_heuristic_effectiveness(engine, failure_threshold=0.5, min_samples=5)
        assert len(result) == 1
        assert result[0].condition == "cond"

    @pytest.mark.asyncio
    async def test_ignores_small_samples(self) -> None:
        engine = AsyncMock()
        engine.get_active_heuristics.return_value = [
            HeuristicRule(
                domain="test",
                condition="cond",
                action="act",
                success_count=0,
                failure_count=2,
            ),
        ]

        result = await review_heuristic_effectiveness(engine, failure_threshold=0.5, min_samples=5)
        assert len(result) == 0
