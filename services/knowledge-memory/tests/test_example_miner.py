"""Tests for the example_miner module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx

from architect_llm.models import LLMResponse
from knowledge_memory.example_miner import mine_examples


def _make_llm_response(content: str) -> LLMResponse:
    """Create a minimal LLMResponse for testing."""
    return LLMResponse(
        content=content,
        model_id="claude-test",
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )


class TestMineExamples:
    """Tests for the mine_examples function."""

    async def test_no_source_urls_returns_llm_generated(self) -> None:
        """Without source URLs, should return LLM-generated examples."""
        examples_json = json.dumps(
            [
                {"title": "Example 1", "content": "print('hello')", "tags": ["python"]},
            ]
        )
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=_make_llm_response(examples_json))

        result = await mine_examples("python basics", mock_client)

        assert len(result) == 1
        assert result[0].title == "Example 1"
        assert result[0].content == "print('hello')"
        assert result[0].tags == ["python"]
        assert result[0].source == "example_mine"
        mock_client.generate.assert_awaited_once()

    async def test_fetch_failure_continues_with_llm(self) -> None:
        """When fetch_documentation raises, should continue and return LLM results."""
        examples_json = json.dumps(
            [
                {"title": "Fallback", "content": "code here", "tags": ["test"]},
            ]
        )
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=_make_llm_response(examples_json))

        with patch(
            "knowledge_memory.example_miner.fetch_documentation",
            side_effect=httpx.HTTPError("connection refused"),
        ):
            result = await mine_examples(
                "python basics",
                mock_client,
                source_urls=["https://example.com/docs"],
            )

        assert len(result) == 1
        assert result[0].title == "Fallback"
        assert result[0].source == "example_mine"

    async def test_invalid_llm_response_returns_fallback(self) -> None:
        """Non-JSON LLM response should produce a single fallback entry."""
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=_make_llm_response("This is not JSON at all"))

        result = await mine_examples("python basics", mock_client)

        assert len(result) == 1
        assert result[0].source == "example_mine:parse_fallback"
        assert result[0].content == "This is not JSON at all"
        assert result[0].title == "Example: python basics"

    async def test_successful_fetch_with_valid_examples(self) -> None:
        """When fetch succeeds, should include source content in LLM prompt."""
        examples_json = json.dumps(
            [
                {"title": "From docs", "content": "from lib import X", "tags": ["lib"]},
                {"title": "Advanced", "content": "X.do()", "tags": ["lib", "advanced"]},
            ]
        )
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=_make_llm_response(examples_json))

        with patch(
            "knowledge_memory.example_miner.fetch_documentation",
            return_value="Documentation content here",
        ):
            result = await mine_examples(
                "lib usage",
                mock_client,
                source_urls=["https://example.com/docs"],
            )

        assert len(result) == 2
        assert result[0].title == "From docs"
        assert result[1].title == "Advanced"
        # Verify the LLM was called with source content in the prompt
        call_args = mock_client.generate.call_args
        request = call_args[0][0]
        assert "Source documentation" in request.messages[0]["content"]

    async def test_multiple_urls_partial_failure(self) -> None:
        """When some URLs fail and some succeed, should use available content."""
        examples_json = json.dumps(
            [
                {"title": "Partial", "content": "partial result", "tags": ["test"]},
            ]
        )
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=_make_llm_response(examples_json))

        call_count = 0

        async def _mock_fetch(url: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPError("first URL fails")
            return "Content from second URL"

        with patch(
            "knowledge_memory.example_miner.fetch_documentation",
            side_effect=_mock_fetch,
        ):
            result = await mine_examples(
                "test topic",
                mock_client,
                source_urls=["https://fail.com", "https://success.com"],
            )

        assert len(result) == 1
        # LLM should have been called with source content from the second URL
        call_args = mock_client.generate.call_args
        request = call_args[0][0]
        assert "Source documentation" in request.messages[0]["content"]
