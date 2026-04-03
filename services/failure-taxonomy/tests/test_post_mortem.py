"""Tests for the PostMortemAnalyzer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from architect_db.models.failure import FailureRecord
from failure_taxonomy.post_mortem_analyzer import PostMortemAnalyzer


def _make_failure_record(
    *,
    failure_code: str = "f6_logic_bug",
    summary: str = "Test failure",
    root_cause: str | None = None,
    severity: str = "medium",
    resolved: bool = False,
) -> FailureRecord:
    """Create a mock FailureRecord for testing."""
    record = MagicMock(spec=FailureRecord)
    record.id = "fail-test-123"
    record.task_id = "task-1"
    record.agent_id = None
    record.project_id = "proj-1"
    record.failure_code = failure_code
    record.severity = severity
    record.summary = summary
    record.root_cause = root_cause
    record.eval_layer = None
    record.error_message = "test error"
    record.stack_trace = None
    record.classified_by = "auto"
    record.confidence = 0.85
    record.resolved = resolved
    return record


class TestPostMortemAnalyzerBasic:
    """Test basic post-mortem analysis without LLM."""

    async def test_analyze_empty_failures(self, post_mortem_analyzer: PostMortemAnalyzer) -> None:
        """Analysis with no failures should return empty analysis."""
        result = await post_mortem_analyzer.analyze("proj-1", [])
        assert result.project_id == "proj-1"
        assert result.failure_summary == {}
        assert result.root_causes == []

    async def test_analyze_groups_by_code(self, post_mortem_analyzer: PostMortemAnalyzer) -> None:
        """Analysis should group failures by failure code."""
        records = [
            _make_failure_record(failure_code="f6_logic_bug"),
            _make_failure_record(failure_code="f6_logic_bug"),
            _make_failure_record(failure_code="f5_dependency_issue"),
        ]
        result = await post_mortem_analyzer.analyze("proj-1", records)
        assert result.failure_summary["f6_logic_bug"] == 2
        assert result.failure_summary["f5_dependency_issue"] == 1

    async def test_analyze_extracts_root_causes(
        self, post_mortem_analyzer: PostMortemAnalyzer
    ) -> None:
        """Analysis should extract root causes from records."""
        records = [
            _make_failure_record(root_cause="Missing validation"),
            _make_failure_record(root_cause=None),
            _make_failure_record(root_cause="Incorrect type cast"),
        ]
        result = await post_mortem_analyzer.analyze("proj-1", records)
        assert len(result.root_causes) == 2
        assert "Missing validation" in result.root_causes

    async def test_analyze_without_llm_returns_basic(
        self, post_mortem_analyzer: PostMortemAnalyzer
    ) -> None:
        """Without LLM, analysis should return basic summary without improvements."""
        records = [_make_failure_record()]
        result = await post_mortem_analyzer.analyze("proj-1", records)
        assert result.prompt_improvements == []
        assert result.adversarial_tests == []
        assert result.heuristic_updates == []
        assert result.topology_recommendations == []


class TestPostMortemAnalyzerWithLLM:
    """Test post-mortem analysis with LLM."""

    async def test_analyze_with_llm_generates_improvements(
        self, post_mortem_analyzer_with_llm: PostMortemAnalyzer, mock_llm_client: AsyncMock
    ) -> None:
        """With LLM, analysis should generate improvements."""
        llm_response = AsyncMock()
        llm_response.content = json.dumps(
            {
                "prompt_improvements": [
                    {
                        "target_agent_type": "coder",
                        "current_prompt_excerpt": "",
                        "suggested_change": "Add import validation",
                        "rationale": "Prevents dependency issues",
                    }
                ],
                "adversarial_tests": [
                    {
                        "test_name": "test_missing_dep",
                        "test_description": "Test with missing dependency",
                        "attack_vector": "Remove import",
                        "expected_behavior": "Graceful error",
                    }
                ],
                "heuristic_updates": [
                    {
                        "domain": "dependency",
                        "condition": "ImportError detected",
                        "action": "Auto-add to requirements",
                        "source_failure_codes": ["f5_dependency_issue"],
                    }
                ],
                "topology_recommendations": [
                    {
                        "recommendation": "Add dependency checker agent",
                        "rationale": "High F5 rate",
                        "estimated_impact": "40% reduction",
                    }
                ],
            }
        )
        mock_llm_client.generate.return_value = llm_response

        records = [
            _make_failure_record(failure_code="f5_dependency_issue"),
            _make_failure_record(failure_code="f5_dependency_issue"),
        ]
        result = await post_mortem_analyzer_with_llm.analyze("proj-1", records)

        assert len(result.prompt_improvements) == 1
        assert result.prompt_improvements[0].target_agent_type == "coder"
        assert len(result.adversarial_tests) == 1
        assert len(result.heuristic_updates) == 1
        assert len(result.topology_recommendations) == 1

    async def test_analyze_llm_failure_falls_back(
        self, post_mortem_analyzer_with_llm: PostMortemAnalyzer, mock_llm_client: AsyncMock
    ) -> None:
        """If LLM fails, analysis should fall back to basic results."""
        mock_llm_client.generate.side_effect = RuntimeError("LLM unavailable")

        records = [_make_failure_record()]
        result = await post_mortem_analyzer_with_llm.analyze("proj-1", records)

        # Should still have basic analysis
        assert result.failure_summary == {"f6_logic_bug": 1}
        # But no LLM-generated improvements
        assert result.prompt_improvements == []
