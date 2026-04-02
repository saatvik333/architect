"""Shared helpers for parsing LLM JSON responses."""

from __future__ import annotations

import json
import re
from typing import Any

_MAX_CONTENT_LENGTH = 50_000  # 50KB max per content field
_MAX_TAGS_COUNT = 50
_MAX_ARRAY_LENGTH = 200


def parse_llm_json_array(content: str, logger: Any) -> list[dict[str, Any]]:
    """Parse an LLM response expected to be a JSON array.

    Handles common LLM quirks: returning a single object instead of an array,
    returning malformed JSON, or wrapping JSON in markdown code fences.

    Args:
        content: Raw LLM response text.
        logger: A structlog logger instance for warnings.

    Returns:
        A list of dicts parsed from the response, or an empty list on failure.
    """
    text = content.strip()
    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            parsed = [result]
        elif isinstance(result, list):
            parsed = result
        else:
            return []

        if len(parsed) > _MAX_ARRAY_LENGTH:
            parsed = parsed[:_MAX_ARRAY_LENGTH]

        for entry in parsed:
            if isinstance(entry, dict):
                content_val = entry.get("content", "")
                if isinstance(content_val, str) and len(content_val) > _MAX_CONTENT_LENGTH:
                    entry["content"] = content_val[:_MAX_CONTENT_LENGTH]
                tags = entry.get("tags", [])
                if isinstance(tags, list) and len(tags) > _MAX_TAGS_COUNT:
                    entry["tags"] = tags[:_MAX_TAGS_COUNT]

        return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("failed_to_parse_llm_json", content_preview=content[:200])
        return []
