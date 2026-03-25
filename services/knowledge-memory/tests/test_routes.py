"""Tests for Knowledge & Memory API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge_memory.api.dependencies import (
    set_heuristic_engine,
    set_knowledge_store,
    set_working_memory,
)
from knowledge_memory.heuristic_engine import HeuristicEngine
from knowledge_memory.knowledge_store import KnowledgeStore
from knowledge_memory.service import create_app
from knowledge_memory.working_memory import WorkingMemoryStore


@pytest.fixture
def mock_store() -> AsyncMock:
    """Create a mock KnowledgeStore."""
    store = AsyncMock(spec=KnowledgeStore)
    store.search.return_value = []
    store.get_entry.return_value = None
    store.get_active_heuristics.return_value = []
    store.get_meta_strategies.return_value = []
    store.get_stats.return_value = {
        "total_entries": 0,
        "entries_by_layer": {},
        "total_observations": 0,
        "total_heuristics": 0,
        "total_meta_strategies": 0,
    }
    return store


@pytest.fixture
def mock_engine(mock_store: AsyncMock) -> HeuristicEngine:
    """Create a HeuristicEngine with mocked store."""
    return HeuristicEngine(knowledge_store=mock_store)


@pytest.fixture
def wm_store() -> WorkingMemoryStore:
    """Create a real WorkingMemoryStore for testing."""
    return WorkingMemoryStore(ttl_seconds=3600, max_entries=100)


@pytest.fixture
def app(mock_store: AsyncMock, mock_engine: HeuristicEngine, wm_store: WorkingMemoryStore):
    """Create a fresh app instance for testing with injected dependencies."""
    set_knowledge_store(mock_store)
    set_heuristic_engine(mock_engine)
    set_working_memory(wm_store)
    return create_app()


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Integration tests for the Knowledge & Memory HTTP API."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "knowledge-memory"

    async def test_query_knowledge(self, client: AsyncClient) -> None:
        """POST /api/v1/knowledge/query should return results."""
        response = await client.post(
            "/api/v1/knowledge/query",
            json={"query": "python testing", "limit": 5},
        )
        assert response.status_code == 200
        body = response.json()
        assert "entries" in body
        assert body["total"] == 0

    async def test_get_knowledge_not_found(self, client: AsyncClient) -> None:
        """GET /api/v1/knowledge/{id} should return 404 for missing entries."""
        response = await client.get("/api/v1/knowledge/know-nonexistent")
        assert response.status_code == 404

    async def test_create_knowledge(self, client: AsyncClient) -> None:
        """POST /api/v1/knowledge should create a new entry."""
        response = await client.post(
            "/api/v1/knowledge",
            json={
                "layer": "l1_project",
                "topic": "python",
                "title": "Test Entry",
                "content": "Some content",
                "content_type": "documentation",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "created"
        assert "id" in body

    async def test_get_stats(self, client: AsyncClient) -> None:
        """GET /api/v1/stats should return statistics."""
        response = await client.get("/api/v1/stats")
        assert response.status_code == 200
        body = response.json()
        assert "total_entries" in body
        assert "entries_by_layer" in body

    async def test_list_heuristics(self, client: AsyncClient) -> None:
        """GET /api/v1/heuristics should return a list."""
        response = await client.get("/api/v1/heuristics")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_match_heuristics(self, client: AsyncClient) -> None:
        """GET /api/v1/heuristics/match should return matching rules."""
        response = await client.get(
            "/api/v1/heuristics/match",
            params={"domain": "testing"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_trigger_acquisition(self, client: AsyncClient) -> None:
        """POST /api/v1/acquire should return accepted status."""
        response = await client.post(
            "/api/v1/acquire",
            json={"topic": "fastapi", "source_urls": ["https://example.com"]},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"

    async def test_trigger_compression(self, client: AsyncClient) -> None:
        """POST /api/v1/compress should return compression result."""
        response = await client.post(
            "/api/v1/compress",
            json={"domain": "testing"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "patterns_created" in body

    async def test_list_meta_strategies(self, client: AsyncClient) -> None:
        """GET /api/v1/meta-strategies should return a list."""
        response = await client.get("/api/v1/meta-strategies")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_working_memory_not_found(self, client: AsyncClient) -> None:
        """GET /api/v1/working-memory/{task_id}/{agent_id} should return 404."""
        response = await client.get("/api/v1/working-memory/task-test001/agent-test001")
        assert response.status_code == 404

    async def test_working_memory_create_and_get(self, client: AsyncClient) -> None:
        """POST then GET working memory should work."""
        # Create
        response = await client.post(
            "/api/v1/working-memory/task-wm001/agent-wm001",
            json={"scratchpad_updates": {"key": "value"}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["task_id"] == "task-wm001"
        assert body["scratchpad"]["key"] == "value"

        # Get
        response = await client.get("/api/v1/working-memory/task-wm001/agent-wm001")
        assert response.status_code == 200
        body = response.json()
        assert body["scratchpad"]["key"] == "value"

    async def test_knowledge_feedback(self, client: AsyncClient, mock_store: AsyncMock) -> None:
        """PUT /api/v1/knowledge/{id}/feedback should record feedback."""
        # Need to make get_entry return something
        mock_store.get_entry.return_value = {
            "id": "know-fb001",
            "layer": "l1_project",
        }

        response = await client.put(
            "/api/v1/knowledge/know-fb001/feedback",
            json={"useful": True, "comment": "Great!"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "feedback_recorded"

    async def test_heuristic_outcome(self, client: AsyncClient) -> None:
        """POST /api/v1/heuristics/{id}/outcome should record outcome."""
        response = await client.post(
            "/api/v1/heuristics/heur-test001/outcome",
            json={"success": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "outcome_recorded"
