"""Tests for the compression pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from architect_common.enums import MemoryLayer
from architect_llm.models import LLMResponse
from knowledge_memory.compression import CompressionPipeline
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.models import CompressionResult


class TestCompressionPipeline:
    """Tests for CompressionPipeline operations."""

    @pytest.fixture
    def mock_store(self) -> AsyncMock:
        """Create a mock KnowledgeStore."""
        return AsyncMock(spec=KnowledgeStore)

    @pytest.fixture
    def mock_heuristic_engine(self) -> AsyncMock:
        """Create a mock HeuristicEngine."""
        return AsyncMock(spec=HeuristicEngine)

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create a mock LLMClient."""
        return AsyncMock()

    @pytest.fixture
    def pipeline(
        self,
        mock_store: AsyncMock,
        mock_heuristic_engine: AsyncMock,
        mock_llm: AsyncMock,
    ) -> CompressionPipeline:
        """Create a CompressionPipeline with mocked dependencies."""
        return CompressionPipeline(
            knowledge_store=mock_store,
            heuristic_engine=mock_heuristic_engine,
            llm_client=mock_llm,
            min_observations=2,
            min_patterns=2,
        )

    # ── compress_observations ────────────────────────────────────────

    async def test_compress_observations_no_observations(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock
    ) -> None:
        """compress_observations with no observations returns empty result."""
        mock_store.get_uncompressed_observations.return_value = []

        result = await pipeline.compress_observations()

        assert isinstance(result, CompressionResult)
        assert result.patterns_created == 0
        assert result.observations_processed == 0

    async def test_compress_observations_with_observations(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        """compress_observations with observations calls store, LLM, and marks compressed."""
        observations = [
            {"id": "know-obs1", "content": "obs 1", "embedding": [0.1, 0.2]},
            {"id": "know-obs2", "content": "obs 2", "embedding": [0.1, 0.3]},
            {"id": "know-obs3", "content": "obs 3", "embedding": [0.9, 0.8]},
        ]
        mock_store.get_uncompressed_observations.return_value = observations

        # Mock cluster_observations and extract_patterns at module level
        fake_pattern = AsyncMock()
        fake_pattern.id = "pat-001"
        fake_pattern.layer = MemoryLayer.L2_PATTERN
        fake_pattern.topic = "testing"
        fake_pattern.title = "Test Pattern"
        fake_pattern.content = "Pattern content"
        fake_pattern.content_type = "pattern"
        fake_pattern.confidence = 0.8
        fake_pattern.tags = ["test"]
        fake_pattern.embedding = [0.1, 0.2]
        fake_pattern.source = "compression"

        with (
            patch(
                "knowledge_memory.compression.cluster_observations",
                return_value=[observations[:2], [observations[2]]],
            ),
            patch(
                "knowledge_memory.compression.extract_patterns",
                return_value=[fake_pattern],
            ),
        ):
            result = await pipeline.compress_observations()

        assert result.observations_processed == 3
        assert result.patterns_created == 1
        mock_store.store_entry.assert_called_once()
        mock_store.mark_observations_compressed.assert_called_once()

    async def test_compress_observations_llm_error(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock
    ) -> None:
        """compress_observations handles LLM errors gracefully."""
        observations = [
            {"id": "know-obs1", "content": "obs 1", "embedding": [0.1, 0.2]},
            {"id": "know-obs2", "content": "obs 2", "embedding": [0.1, 0.3]},
        ]
        mock_store.get_uncompressed_observations.return_value = observations

        with (
            patch(
                "knowledge_memory.compression.cluster_observations",
                return_value=[observations],
            ),
            patch(
                "knowledge_memory.compression.extract_patterns",
                side_effect=RuntimeError("LLM unavailable"),
            ),
            pytest.raises(RuntimeError, match="LLM unavailable"),
        ):
            await pipeline.compress_observations()

    # ── promote_patterns_to_heuristics ───────────────────────────────

    async def test_promote_patterns_insufficient(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock
    ) -> None:
        """promote_patterns_to_heuristics with insufficient patterns returns empty."""
        mock_store.search.return_value = [{"title": "only one"}]

        result = await pipeline.promote_patterns_to_heuristics()

        assert result == []
        mock_store.store_heuristic.assert_not_called()

    async def test_promote_patterns_with_enough_patterns(
        self,
        pipeline: CompressionPipeline,
        mock_store: AsyncMock,
        mock_heuristic_engine: AsyncMock,
    ) -> None:
        """promote_patterns_to_heuristics with enough patterns synthesizes and stores."""
        patterns = [
            {"title": "Pattern 1", "content": "p1"},
            {"title": "Pattern 2", "content": "p2"},
            {"title": "Pattern 3", "content": "p3"},
        ]
        mock_store.search.return_value = patterns

        fake_rule = MagicMock()
        fake_rule.model_dump.return_value = {
            "id": "heur-001",
            "domain": "testing",
            "condition": "When X",
            "action": "Do Y",
        }
        mock_heuristic_engine.synthesize_heuristics.return_value = [fake_rule]

        result = await pipeline.promote_patterns_to_heuristics()

        assert len(result) == 1
        assert result[0]["id"] == "heur-001"
        mock_store.store_heuristic.assert_called_once()

    # ── derive_meta_strategies ───────────────────────────────────────

    async def test_derive_meta_strategies_no_heuristics(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock
    ) -> None:
        """derive_meta_strategies with no heuristics returns empty."""
        mock_store.get_active_heuristics.return_value = []

        result = await pipeline.derive_meta_strategies()

        assert result == []

    async def test_derive_meta_strategies_with_heuristics(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        """derive_meta_strategies with heuristics calls LLM and returns strategies."""
        mock_store.get_active_heuristics.return_value = [
            {
                "id": "heur-001",
                "domain": "testing",
                "condition": "When tests fail",
                "action": "Add assertions",
                "confidence": 0.8,
            },
        ]

        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps(
                [
                    {
                        "name": "Test-First Strategy",
                        "description": "Write tests before code",
                        "steps": ["Write test", "Implement", "Refactor"],
                        "confidence": 0.9,
                    }
                ]
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        result = await pipeline.derive_meta_strategies()

        assert len(result) == 1
        assert result[0].name == "Test-First Strategy"
        assert result[0].confidence == 0.9
        mock_llm.generate.assert_called_once()
        mock_store.store_meta_strategy.assert_called_once()

    async def test_derive_meta_strategies_llm_bad_json(
        self, pipeline: CompressionPipeline, mock_store: AsyncMock, mock_llm: AsyncMock
    ) -> None:
        """derive_meta_strategies with bad LLM JSON returns empty list."""
        mock_store.get_active_heuristics.return_value = [
            {
                "id": "heur-001",
                "domain": "testing",
                "condition": "When tests fail",
                "action": "Add assertions",
                "confidence": 0.8,
            },
        ]

        mock_llm.generate.return_value = LLMResponse(
            content="not valid json {{{",
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        result = await pipeline.derive_meta_strategies()

        assert result == []
