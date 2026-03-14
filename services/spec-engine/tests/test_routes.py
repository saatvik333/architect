"""Tests for spec-engine API routes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from architect_llm.client import LLMClient
from architect_llm.models import LLMResponse
from spec_engine.api.dependencies import get_spec_parser
from spec_engine.parser import SpecParser
from spec_engine.service import app


def _build_mock_parser() -> SpecParser:
    """Build a SpecParser backed by a mock LLM client."""
    spec_json = json.dumps(
        {
            "type": "spec",
            "intent": "Add a greeting function",
            "constraints": ["No external deps"],
            "success_criteria": [
                {"description": "Returns greeting", "test_type": "unit", "automated": True}
            ],
            "file_targets": ["src/hello.py"],
            "assumptions": [],
            "open_questions": [],
        }
    )

    mock_client = AsyncMock(spec=LLMClient)
    mock_client.generate.return_value = LLMResponse(
        content=spec_json,
        model_id="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=100,
        stop_reason="end_turn",
    )

    return SpecParser(mock_client)


@pytest.fixture(autouse=True)
def _override_parser_dep():
    """Override the spec parser dependency with a mock-backed instance."""
    mock_parser = _build_mock_parser()

    async def _override() -> SpecParser:
        return mock_parser

    app.dependency_overrides[get_spec_parser] = _override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    """Return an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRoutes:
    """Tests for API routes."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """GET /health returns healthy status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "spec-engine"

    async def test_create_spec(self, client: AsyncClient) -> None:
        """POST /api/v1/specs returns a parsed spec."""
        resp = await client.post(
            "/api/v1/specs",
            json={"raw_text": "Add a greeting function"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["spec"] is not None
        assert data["result"]["spec"]["intent"] == "Add a greeting function"

    async def test_get_spec(self, client: AsyncClient) -> None:
        """GET /api/v1/specs/{id} retrieves a stored spec."""
        # First create a spec
        create_resp = await client.post(
            "/api/v1/specs",
            json={"raw_text": "Build something"},
        )
        spec_id = create_resp.json()["result"]["spec"]["id"]

        # Then retrieve it
        resp = await client.get(f"/api/v1/specs/{spec_id}")
        assert resp.status_code == 200
        assert resp.json()["result"]["spec"]["id"] == spec_id

    async def test_get_spec_not_found(self, client: AsyncClient) -> None:
        """GET /api/v1/specs/{id} returns 404 for unknown ID."""
        resp = await client.get("/api/v1/specs/spec-nonexistent")
        assert resp.status_code == 404

    async def test_clarify_spec(self, client: AsyncClient) -> None:
        """POST /api/v1/specs/{id}/clarify accepts clarifications."""
        # First create a spec
        create_resp = await client.post(
            "/api/v1/specs",
            json={"raw_text": "Build an API"},
        )
        spec_id = create_resp.json()["result"]["spec"]["id"]

        # Then clarify it
        resp = await client.post(
            f"/api/v1/specs/{spec_id}/clarify",
            json={"clarifications": {"What language?": "Python"}},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["spec"] is not None
