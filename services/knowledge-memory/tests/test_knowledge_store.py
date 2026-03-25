"""Tests for the KnowledgeStore data access layer (mocked DB)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from architect_common.enums import ContentType, MemoryLayer, ObservationType
from architect_common.types import AgentId, KnowledgeId, PatternId, TaskId
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.similarity import cosine_similarity


class TestCosineSimilarity:
    """Tests for the cosine similarity helper."""

    def test_identical_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_empty_vectors(self) -> None:
        assert cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self) -> None:
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_zero_vectors(self) -> None:
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_similar_vectors(self) -> None:
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        sim = cosine_similarity(a, b)
        assert 0.5 < sim < 1.0


class TestKnowledgeStore:
    """Tests for KnowledgeStore with mocked database sessions."""

    @pytest.fixture
    def mock_session_factory(self) -> AsyncMock:
        """Create a mock async session factory."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        # Make the context manager work
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)

        return factory

    @pytest.fixture
    def store(self, mock_session_factory: AsyncMock) -> KnowledgeStore:
        """Create a KnowledgeStore with mocked session factory."""
        return KnowledgeStore(mock_session_factory)

    async def test_store_entry(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """store_entry should execute an INSERT query."""
        await store.store_entry(
            entry_id=KnowledgeId("know-test001"),
            layer=MemoryLayer.L1_PROJECT,
            topic="python",
            title="Test Entry",
            content="Some test content",
            content_type=ContentType.DOCUMENTATION,
        )

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_called()
        session.commit.assert_called()

    async def test_store_observation(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """store_observation should execute an INSERT query."""
        await store.store_observation(
            obs_id=KnowledgeId("know-obs001"),
            task_id=TaskId("task-test001"),
            agent_id=AgentId("agent-test001"),
            observation_type=ObservationType.SUCCESS,
            description="Test observation",
        )

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_called()
        session.commit.assert_called()

    async def test_get_entry_found(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """get_entry should return a dict when entry exists."""
        session = mock_session_factory.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_mapping = MagicMock()
        mock_mapping.first.return_value = {
            "id": "know-test001",
            "layer": "l1_project",
            "topic": "python",
        }
        mock_result.mappings.return_value = mock_mapping
        session.execute.return_value = mock_result

        entry = await store.get_entry(KnowledgeId("know-test001"))
        assert entry is not None
        assert entry["id"] == "know-test001"

    async def test_get_entry_not_found(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """get_entry should return None when entry does not exist."""
        session = mock_session_factory.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_mapping = MagicMock()
        mock_mapping.first.return_value = None
        mock_result.mappings.return_value = mock_mapping
        session.execute.return_value = mock_result

        entry = await store.get_entry(KnowledgeId("know-nonexistent"))
        assert entry is None

    async def test_increment_usage(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """increment_usage should execute an UPDATE query."""
        await store.increment_usage(KnowledgeId("know-test001"))

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_called()
        session.commit.assert_called()

    async def test_deactivate_entry(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """deactivate_entry should execute an UPDATE setting active=false."""
        await store.deactivate_entry(KnowledgeId("know-test001"))

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_called()
        session.commit.assert_called()

    async def test_search_returns_sorted_by_similarity(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """search should return entries sorted by cosine similarity."""
        session = mock_session_factory.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"id": "know-1", "embedding": [1.0, 0.0, 0.0]},
            {"id": "know-2", "embedding": [0.9, 0.1, 0.0]},
            {"id": "know-3", "embedding": [0.0, 0.0, 1.0]},
        ]
        session.execute.return_value = mock_result

        results = await store.search(
            query_embedding=[1.0, 0.0, 0.0],
            limit=3,
        )

        assert len(results) == 3
        # First result should be most similar
        assert results[0]["id"] == "know-1"

    async def test_mark_observations_compressed(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """mark_observations_compressed should update the compressed flag."""
        obs_ids = [KnowledgeId("know-obs1"), KnowledgeId("know-obs2")]
        pattern_id = PatternId("pat-test001")

        await store.mark_observations_compressed(obs_ids, pattern_id)

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_called()

    async def test_mark_observations_compressed_empty(
        self, store: KnowledgeStore, mock_session_factory: AsyncMock
    ) -> None:
        """mark_observations_compressed with empty list should be a no-op."""
        await store.mark_observations_compressed([], PatternId("pat-test001"))

        session = mock_session_factory.return_value.__aenter__.return_value
        session.execute.assert_not_called()
