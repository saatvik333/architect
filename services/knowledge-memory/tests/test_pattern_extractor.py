"""Tests for pattern extraction (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from architect_llm.models import LLMResponse
from knowledge_memory.pattern_extractor import (
    cluster_observations,
    extract_patterns,
)


class TestClusterObservations:
    """Tests for the observation clustering function."""

    def test_empty_input(self) -> None:
        result = cluster_observations([])
        assert result == []

    def test_single_observation(self) -> None:
        obs = [{"id": "1", "embedding": [1.0, 0.0, 0.0], "description": "test"}]
        result = cluster_observations(obs)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_similar_observations_cluster_together(self) -> None:
        obs = [
            {"id": "1", "embedding": [1.0, 0.0, 0.0], "description": "test 1"},
            {"id": "2", "embedding": [0.95, 0.05, 0.0], "description": "test 2"},
            {"id": "3", "embedding": [0.0, 0.0, 1.0], "description": "test 3"},
        ]
        result = cluster_observations(obs, similarity_threshold=0.8)
        # First two should cluster together, third separate
        assert len(result) >= 2

    def test_observations_without_embeddings(self) -> None:
        obs = [
            {"id": "1", "description": "no embedding"},
            {"id": "2", "embedding": [], "description": "empty embedding"},
        ]
        result = cluster_observations(obs)
        # Each should be in its own cluster
        assert len(result) == 2

    def test_all_similar_one_cluster(self) -> None:
        obs = [
            {"id": "1", "embedding": [1.0, 0.0], "description": "a"},
            {"id": "2", "embedding": [0.99, 0.01], "description": "b"},
            {"id": "3", "embedding": [0.98, 0.02], "description": "c"},
        ]
        result = cluster_observations(obs, similarity_threshold=0.9)
        # All should end up in one cluster
        total_obs = sum(len(c) for c in result)
        assert total_obs == 3


class TestExtractPatterns:
    """Tests for LLM-powered pattern extraction."""

    async def test_extract_patterns_success(self) -> None:
        """extract_patterns should parse LLM JSON response into KnowledgeEntry objects."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps(
                [
                    {
                        "title": "Error Handling Pattern",
                        "content": "Always wrap database calls in try-except blocks",
                        "confidence": 0.8,
                        "tags": ["error-handling", "database"],
                    }
                ]
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        observations = [
            {
                "id": "obs-1",
                "observation_type": "failure",
                "description": "Database timeout",
                "domain": "database",
                "outcome": "failed",
            },
            {
                "id": "obs-2",
                "observation_type": "success",
                "description": "Database retry succeeded",
                "domain": "database",
                "outcome": "success",
            },
        ]

        patterns = await extract_patterns(observations, mock_llm)
        assert len(patterns) == 1
        assert patterns[0].title == "Error Handling Pattern"
        assert patterns[0].layer == "l2_pattern"
        assert patterns[0].content_type == "pattern"
        assert patterns[0].confidence == 0.8

    async def test_extract_patterns_empty_input(self) -> None:
        """extract_patterns with empty input should return empty list."""
        mock_llm = AsyncMock()
        patterns = await extract_patterns([], mock_llm)
        assert patterns == []

    async def test_extract_patterns_parse_fallback(self) -> None:
        """extract_patterns should handle non-JSON LLM responses gracefully."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content="This is not valid JSON but contains useful pattern info.",
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        observations = [
            {
                "id": "obs-1",
                "observation_type": "success",
                "description": "Test",
                "domain": "general",
                "outcome": "success",
            },
        ]

        patterns = await extract_patterns(observations, mock_llm)
        assert len(patterns) == 1
        assert patterns[0].confidence == 0.3  # fallback confidence
        assert "parse_fallback" in patterns[0].source

    async def test_extract_patterns_multiple(self) -> None:
        """extract_patterns should handle multiple patterns from LLM."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps(
                [
                    {
                        "title": "Pattern A",
                        "content": "First pattern",
                        "confidence": 0.9,
                        "tags": ["a"],
                    },
                    {
                        "title": "Pattern B",
                        "content": "Second pattern",
                        "confidence": 0.7,
                        "tags": ["b"],
                    },
                ]
            ),
            model_id="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=100,
            stop_reason="end_turn",
        )

        observations = [
            {
                "id": "obs-1",
                "observation_type": "success",
                "description": "Test",
                "domain": "general",
                "outcome": "ok",
            }
        ]
        patterns = await extract_patterns(observations, mock_llm)
        assert len(patterns) == 2
