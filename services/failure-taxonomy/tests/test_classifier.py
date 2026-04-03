"""Tests for the FailureClassifier — rule-based classification for F1-F9."""

from __future__ import annotations

import json

from architect_common.enums import FailureCode
from failure_taxonomy.classifier import FailureClassifier
from failure_taxonomy.models import ClassificationRequest


class TestRuleBasedClassification:
    """Test each F1-F9 rule-based classification path."""

    async def test_f5_import_error(self, classifier: FailureClassifier) -> None:
        """ImportError should classify as F5_DEPENDENCY_ISSUE."""
        request = ClassificationRequest(
            task_id="task-1",
            error_message="ImportError: No module named 'pandas'",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F5_DEPENDENCY_ISSUE
        assert result.confidence >= 0.7

    async def test_f5_module_not_found(self, classifier: FailureClassifier) -> None:
        """ModuleNotFoundError should classify as F5."""
        request = ClassificationRequest(
            task_id="task-2",
            error_message="ModuleNotFoundError: No module named 'nonexistent'",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F5_DEPENDENCY_ISSUE

    async def test_f6_syntax_error(self, classifier: FailureClassifier) -> None:
        """SyntaxError should classify as F6_LOGIC_BUG."""
        request = ClassificationRequest(
            task_id="task-3",
            error_message="SyntaxError: invalid syntax at line 42",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG

    async def test_f6_indentation_error(self, classifier: FailureClassifier) -> None:
        """IndentationError should classify as F6."""
        request = ClassificationRequest(
            task_id="task-4",
            error_message="IndentationError: unexpected indent",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG

    async def test_f4_tool_failure(self, classifier: FailureClassifier) -> None:
        """Build tool failures should classify as F4_TOOL_FAILURE."""
        request = ClassificationRequest(
            task_id="task-5",
            error_message="CompilationError: gcc failed with exit code 1",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F4_TOOL_FAILURE

    async def test_f4_subprocess_failed(self, classifier: FailureClassifier) -> None:
        """subprocess failure should classify as F4."""
        request = ClassificationRequest(
            task_id="task-6",
            error_message="subprocess.CalledProcessError: subprocess returned failed exit code",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F4_TOOL_FAILURE

    async def test_f9_security_vulnerability(self, classifier: FailureClassifier) -> None:
        """Security findings should classify as F9_SECURITY_VULN."""
        request = ClassificationRequest(
            task_id="task-7",
            error_message="Security vulnerability found: CVE-2024-1234 in dependency",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F9_SECURITY_VULN

    async def test_f9_injection(self, classifier: FailureClassifier) -> None:
        """SQL injection should classify as F9."""
        request = ClassificationRequest(
            task_id="task-8",
            error_message="SQL injection vulnerability detected in user input handler",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F9_SECURITY_VULN

    async def test_f8_performance_regression(self, classifier: FailureClassifier) -> None:
        """Performance regression should classify as F8_PERF_REGRESSION."""
        request = ClassificationRequest(
            task_id="task-9",
            error_message="Performance regression detected: response time increased by 200%",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F8_PERF_REGRESSION

    async def test_f8_timeout(self, classifier: FailureClassifier) -> None:
        """Timeout should classify as F8."""
        request = ClassificationRequest(
            task_id="task-10",
            error_message="Request timeout after 30 seconds",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F8_PERF_REGRESSION

    async def test_f1_spec_compliance(self, classifier: FailureClassifier) -> None:
        """Spec compliance failure should classify as F1_SPEC_AMBIGUITY."""
        request = ClassificationRequest(
            task_id="task-11",
            error_message="Specification compliance failure: missing required endpoint",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F1_SPEC_AMBIGUITY

    async def test_f2_architecture_violation(self, classifier: FailureClassifier) -> None:
        """Architecture violation should classify as F2_ARCHITECTURE_ERROR."""
        request = ClassificationRequest(
            task_id="task-12",
            error_message="Architecture violation: circular dependency detected between modules",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F2_ARCHITECTURE_ERROR

    async def test_f3_hallucination(self, classifier: FailureClassifier) -> None:
        """Non-existent API reference should classify as F3_HALLUCINATION."""
        request = ClassificationRequest(
            task_id="task-13",
            error_message="AttributeError: module 'requests' has no attribute 'send_async'",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F3_HALLUCINATION

    async def test_f3_name_error(self, classifier: FailureClassifier) -> None:
        """NameError for undefined reference should classify as F3."""
        request = ClassificationRequest(
            task_id="task-14",
            error_message="NameError: name 'nonexistent_function' is not defined",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F3_HALLUCINATION

    async def test_f7_ux_rejection(self, classifier: FailureClassifier) -> None:
        """UX rejection should classify as F7_UX_REJECTION."""
        request = ClassificationRequest(
            task_id="task-15",
            error_message="UX review failed: poor user experience in form layout",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F7_UX_REJECTION


class TestEvalLayerFallback:
    """Test classification when no pattern matches but eval layer is provided."""

    async def test_compilation_layer_default(self, classifier: FailureClassifier) -> None:
        """Compilation layer with no matching pattern should default to F6."""
        request = ClassificationRequest(
            task_id="task-20",
            error_message="Unknown error occurred",
            eval_layer="compilation",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG

    async def test_adversarial_layer_default(self, classifier: FailureClassifier) -> None:
        """Adversarial layer should default to F9."""
        request = ClassificationRequest(
            task_id="task-21",
            error_message="Unknown error occurred",
            eval_layer="adversarial",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F9_SECURITY_VULN

    async def test_spec_compliance_layer_default(self, classifier: FailureClassifier) -> None:
        """Spec compliance layer should default to F1."""
        request = ClassificationRequest(
            task_id="task-22",
            error_message="Unknown error occurred",
            eval_layer="spec_compliance",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F1_SPEC_AMBIGUITY

    async def test_architecture_layer_default(self, classifier: FailureClassifier) -> None:
        """Architecture layer should default to F2."""
        request = ClassificationRequest(
            task_id="task-23",
            error_message="Unknown error occurred",
            eval_layer="architecture",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F2_ARCHITECTURE_ERROR


class TestFallbackBehavior:
    """Test fallback when nothing matches."""

    async def test_no_match_no_layer(self, classifier: FailureClassifier) -> None:
        """With no matching pattern and no eval layer, default to F6."""
        request = ClassificationRequest(
            task_id="task-30",
            error_message="Something completely unrecognizable went wrong",
        )
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG
        assert result.confidence <= 0.5

    async def test_empty_error_no_layer(self, classifier: FailureClassifier) -> None:
        """With no error message and no layer, default to F6."""
        request = ClassificationRequest(task_id="task-31")
        result = await classifier.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG
        assert result.confidence <= 0.5


class TestLLMFallback:
    """Test LLM fallback classification."""

    async def test_llm_called_for_low_confidence(
        self, classifier_with_llm: FailureClassifier, mock_llm_client: object
    ) -> None:
        """LLM should be called when rule-based confidence is low."""
        from unittest.mock import AsyncMock

        llm_client = mock_llm_client
        assert isinstance(llm_client, AsyncMock)

        llm_response = AsyncMock()
        llm_response.content = json.dumps(
            {
                "failure_code": "f6_logic_bug",
                "confidence": 0.8,
                "summary": "Logic error in loop",
                "root_cause": "Off-by-one error",
                "suggested_fix": "Fix loop bounds",
            }
        )
        llm_client.generate.return_value = llm_response

        request = ClassificationRequest(
            task_id="task-40",
            error_message="Something completely unrecognizable went wrong",
        )
        result = await classifier_with_llm.classify(request)
        assert result.failure_code == FailureCode.F6_LOGIC_BUG
        assert result.confidence == 0.8
        llm_client.generate.assert_called_once()

    async def test_llm_failure_falls_back_to_rules(
        self, classifier_with_llm: FailureClassifier, mock_llm_client: object
    ) -> None:
        """If LLM fails, fall back to rule result or default."""
        from unittest.mock import AsyncMock

        llm_client = mock_llm_client
        assert isinstance(llm_client, AsyncMock)
        llm_client.generate.side_effect = RuntimeError("LLM unavailable")

        request = ClassificationRequest(
            task_id="task-41",
            error_message="Something completely unrecognizable went wrong",
        )
        result = await classifier_with_llm.classify(request)
        # Should still get a result (fallback)
        assert result.failure_code is not None
