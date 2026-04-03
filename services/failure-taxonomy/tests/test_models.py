"""Tests for Failure Taxonomy domain models."""

from __future__ import annotations

import pytest

from architect_common.enums import FailureCode
from failure_taxonomy.models import (
    AdversarialTest,
    ClassificationRequest,
    FailureClassification,
    HeuristicUpdate,
    PostMortemAnalysis,
    PromptImprovement,
    SimulationConfig,
    SimulationResult,
    TopologyRecommendation,
)


class TestFailureClassification:
    """Tests for FailureClassification model."""

    def test_create_classification(self) -> None:
        c = FailureClassification(
            failure_code=FailureCode.F6_LOGIC_BUG,
            confidence=0.85,
            summary="Logic bug in generated code",
        )
        assert c.failure_code == FailureCode.F6_LOGIC_BUG
        assert c.confidence == 0.85
        assert c.summary == "Logic bug in generated code"
        assert c.root_cause is None
        assert c.suggested_fix is None

    def test_classification_with_all_fields(self) -> None:
        c = FailureClassification(
            failure_code=FailureCode.F9_SECURITY_VULN,
            confidence=0.95,
            summary="SQL injection vulnerability",
            root_cause="Unsanitized user input in query",
            suggested_fix="Use parameterized queries",
        )
        assert c.root_cause == "Unsanitized user input in query"
        assert c.suggested_fix == "Use parameterized queries"

    def test_classification_frozen(self) -> None:
        c = FailureClassification(
            failure_code=FailureCode.F1_SPEC_AMBIGUITY,
            confidence=0.7,
            summary="Ambiguous spec",
        )
        with pytest.raises((TypeError, ValueError)):
            c.confidence = 0.9  # type: ignore[misc]

    def test_confidence_bounds(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            FailureClassification(
                failure_code=FailureCode.F6_LOGIC_BUG,
                confidence=1.5,
                summary="Out of bounds",
            )


class TestClassificationRequest:
    """Tests for ClassificationRequest model."""

    def test_minimal_request(self) -> None:
        r = ClassificationRequest(task_id="task-123")
        assert r.task_id == "task-123"
        assert r.error_message == ""
        assert r.agent_id is None

    def test_full_request(self) -> None:
        r = ClassificationRequest(
            task_id="task-123",
            agent_id="agent-456",
            error_message="ImportError: No module named foo",
            stack_trace="Traceback...",
            eval_layer="compilation",
            eval_report={"verdict": "fail_hard"},
            code_context="import foo",
        )
        assert r.agent_id == "agent-456"
        assert r.eval_layer == "compilation"


class TestPostMortemAnalysis:
    """Tests for PostMortemAnalysis model."""

    def test_empty_analysis(self) -> None:
        from architect_common.types import new_post_mortem_id

        pm = PostMortemAnalysis(
            post_mortem_id=new_post_mortem_id(),
            project_id="proj-1",
        )
        assert pm.project_id == "proj-1"
        assert pm.failure_summary == {}
        assert pm.root_causes == []
        assert pm.prompt_improvements == []

    def test_analysis_with_improvements(self) -> None:
        from architect_common.types import new_post_mortem_id

        pm = PostMortemAnalysis(
            post_mortem_id=new_post_mortem_id(),
            project_id="proj-1",
            failure_summary={"f6_logic_bug": 5, "f5_dependency_issue": 2},
            root_causes=["Missing validation", "Incorrect import"],
            prompt_improvements=[
                PromptImprovement(
                    target_agent_type="coder",
                    suggested_change="Add import validation step",
                    rationale="Prevents F5 failures",
                ),
            ],
            adversarial_tests=[
                AdversarialTest(
                    test_name="test_missing_import",
                    test_description="Test with missing dependency",
                    attack_vector="Remove a required import",
                    expected_behavior="Agent should detect and add import",
                ),
            ],
        )
        assert len(pm.prompt_improvements) == 1
        assert len(pm.adversarial_tests) == 1


class TestSimulationModels:
    """Tests for simulation config and result models."""

    def test_simulation_config_defaults(self) -> None:
        c = SimulationConfig()
        assert c.source_type == "manual"
        assert c.bug_injection_count == 5
        assert c.max_duration_seconds == 300

    def test_simulation_result(self) -> None:
        r = SimulationResult(
            failures_injected=10,
            failures_detected=8,
            detection_rate=0.8,
            missed_failures=["bug_1", "bug_2"],
            false_positives=[],
        )
        assert r.detection_rate == 0.8
        assert len(r.missed_failures) == 2


class TestSupportModels:
    """Tests for HeuristicUpdate and TopologyRecommendation."""

    def test_heuristic_update(self) -> None:
        h = HeuristicUpdate(
            domain="testing",
            condition="ImportError detected",
            action="Add dependency to requirements",
            source_failure_codes=[FailureCode.F5_DEPENDENCY_ISSUE],
        )
        assert h.domain == "testing"
        assert len(h.source_failure_codes) == 1

    def test_topology_recommendation(self) -> None:
        t = TopologyRecommendation(
            recommendation="Add dedicated dependency checker agent",
            rationale="High F5 failure rate",
            estimated_impact="Reduce F5 failures by ~40%",
        )
        assert t.estimated_impact == "Reduce F5 failures by ~40%"
