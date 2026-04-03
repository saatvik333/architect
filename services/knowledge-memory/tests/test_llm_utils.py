"""Tests for the LLM JSON parsing utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from knowledge_memory.llm_utils import parse_llm_json_array


class TestParseLlmJsonArray:
    """Verify parse_llm_json_array handles common LLM response formats."""

    def _logger(self) -> MagicMock:
        return MagicMock()

    def test_valid_json_array(self) -> None:
        """A valid JSON array should be returned as-is."""
        content = '[{"title": "A"}, {"title": "B"}]'
        result = parse_llm_json_array(content, self._logger())
        assert result == [{"title": "A"}, {"title": "B"}]

    def test_single_json_object_wrapped_in_list(self) -> None:
        """A single JSON object should be wrapped in a list."""
        content = '{"title": "Solo"}'
        result = parse_llm_json_array(content, self._logger())
        assert result == [{"title": "Solo"}]

    def test_malformed_json_returns_empty_list(self) -> None:
        """Malformed JSON should return an empty list."""
        logger = self._logger()
        content = "{not valid json"
        result = parse_llm_json_array(content, logger)
        assert result == []
        logger.warning.assert_called_once()

    def test_empty_string_returns_empty_list(self) -> None:
        """An empty string should return an empty list."""
        logger = self._logger()
        result = parse_llm_json_array("", logger)
        assert result == []
        logger.warning.assert_called_once()

    def test_markdown_fenced_json(self) -> None:
        """Markdown-fenced JSON should be stripped and parsed."""
        content = '```json\n[{"title": "Fenced"}]\n```'
        result = parse_llm_json_array(content, self._logger())
        assert result == [{"title": "Fenced"}]

    def test_markdown_fenced_without_language(self) -> None:
        """Markdown fences without a language tag should still be stripped."""
        content = '```\n{"key": "value"}\n```'
        result = parse_llm_json_array(content, self._logger())
        assert result == [{"key": "value"}]

    def test_non_dict_non_list_json_returns_empty_list(self) -> None:
        """A JSON value that is not a dict or list should return an empty list."""
        result = parse_llm_json_array("42", self._logger())
        assert result == []

    def test_json_string_value_returns_empty_list(self) -> None:
        """A JSON string value should return an empty list."""
        result = parse_llm_json_array('"just a string"', self._logger())
        assert result == []

    def test_json_boolean_returns_empty_list(self) -> None:
        """A JSON boolean should return an empty list."""
        result = parse_llm_json_array("true", self._logger())
        assert result == []

    def test_whitespace_around_content(self) -> None:
        """Leading/trailing whitespace should be stripped before parsing."""
        content = '  \n  [{"title": "spaced"}]  \n  '
        result = parse_llm_json_array(content, self._logger())
        assert result == [{"title": "spaced"}]
