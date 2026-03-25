"""Tests for the heuristic engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from architect_common.types import HeuristicId
from architect_llm.models import LLMResponse
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore


class TestHeuristicEngine:
    """Tests for HeuristicEngine operations."""

    @pytest.fixture
    def mock_store(self) -> AsyncMock:
        """Create a mock KnowledgeStore."""
        store = AsyncMock(spec=KnowledgeStore)
        return store

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create a mock LLMClient."""
        return AsyncMock()

    @pytest.fixture
    def engine(self, mock_store: AsyncMock, mock_llm: AsyncMock) -> HeuristicEngine:
        """Create a HeuristicEngine with mocked dependencies."""
        return HeuristicEngine(knowledge_store=mock_store, llm_client=mock_llm)

    async def test_match_heuristics_returns_rules(
        self, engine: HeuristicEngine, mock_store: AsyncMock
    ) -> None:
        """match_heuristics should convert raw DB rows to HeuristicRule objects."""
        mock_store.get_active_heuristics.return_value = [
            {
                "id": "heur-test001",
                "domain": "testing",
                "condition": "When writing unit tests",
                "action": "Use pytest fixtures",
                "rationale": "Fixtures reduce boilerplate",
                "confidence": 0.8,
                "success_count": 10,
                "failure_count": 2,
                "active": True,
                "source_pattern_ids": '["pat-001"]',
            }
        ]

        rules = await engine.match_heuristics(domain="testing")
        assert len(rules) == 1
        assert rules[0].id == "heur-test001"
        assert rules[0].confidence == 0.8

    async def test_match_heuristics_empty(
        self, engine: HeuristicEngine, mock_store: AsyncMock
    ) -> None:
        """match_heuristics should return empty list when no heuristics exist."""
        mock_store.get_active_heuristics.return_value = []

        rules = await engine.match_heuristics(domain="testing")
        assert rules == []

    async def test_evolve_heuristic_success(
        self, engine: HeuristicEngine, mock_store: AsyncMock
    ) -> None:
        """evolve_heuristic should call update_heuristic_outcome."""
        await engine.evolve_heuristic(HeuristicId("heur-test001"), success=True)
        mock_store.update_heuristic_outcome.assert_called_once_with(
            HeuristicId("heur-test001"), success=True
        )

    async def test_evolve_heuristic_failure(
        self, engine: HeuristicEngine, mock_store: AsyncMock
    ) -> None:
        """evolve_heuristic should pass failure flag through."""
        await engine.evolve_heuristic(HeuristicId("heur-test002"), success=False)
        mock_store.update_heuristic_outcome.assert_called_once_with(
            HeuristicId("heur-test002"), success=False
        )

    async def test_synthesize_heuristics(
        self, engine: HeuristicEngine, mock_llm: AsyncMock
    ) -> None:
        """synthesize_heuristics should use LLM to generate rules from patterns."""
        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps(
                [
                    {
                        "domain": "testing",
                        "condition": "When test coverage is low",
                        "action": "Add property-based tests",
                        "rationale": "Property tests find edge cases",
                        "confidence": 0.7,
                    }
                ]
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        patterns = [
            {"title": "Test Pattern 1", "content": "Pattern about testing", "topic": "testing"},
        ]

        rules = await engine.synthesize_heuristics(patterns)
        assert len(rules) == 1
        assert rules[0].domain == "testing"
        assert rules[0].condition == "When test coverage is low"

    async def test_synthesize_heuristics_no_llm(self, mock_store: AsyncMock) -> None:
        """synthesize_heuristics without LLM client should return empty list."""
        engine = HeuristicEngine(knowledge_store=mock_store, llm_client=None)
        rules = await engine.synthesize_heuristics([{"title": "test"}])
        assert rules == []

    async def test_synthesize_heuristics_empty_patterns(self, engine: HeuristicEngine) -> None:
        """synthesize_heuristics with empty patterns should return empty list."""
        rules = await engine.synthesize_heuristics([])
        assert rules == []
