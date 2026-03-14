"""Tests for the FastAPI routes."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from codebase_comprehension.service import create_app


@pytest.fixture
def app():
    """Return a fresh FastAPI app for each test."""
    return create_app()


@pytest.fixture
async def client(app):
    """Return an async HTTP client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for the Codebase Comprehension API routes."""

    async def test_health_endpoint(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "codebase-comprehension"

    async def test_post_index(self, client: AsyncClient) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a sample Python file
            py_file = Path(tmpdir) / "hello.py"
            py_file.write_text('def hello():\n    return "world"\n')

            resp = await client.post(
                "/api/v1/index",
                json={"directory": tmpdir},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_files"] == 1
            assert data["total_symbols"] >= 1
            assert data["root_path"] == tmpdir

    async def test_get_symbols(self, client: AsyncClient) -> None:
        # First, index a directory
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "math_utils.py"
            py_file.write_text("def add(a, b):\n    return a + b\n")

            await client.post("/api/v1/index", json={"directory": tmpdir})

            resp = await client.get("/api/v1/symbols", params={"query": "add"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            assert any(s["name"] == "add" for s in data["symbols"])

    async def test_get_context(self, client: AsyncClient) -> None:
        # First, index a directory
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "service.py"
            py_file.write_text("def serve():\n    pass\n")

            await client.post("/api/v1/index", json={"directory": tmpdir})

            resp = await client.get(
                "/api/v1/context",
                params={"task_description": "serve"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "relevant_files" in data
            assert "related_symbols" in data
