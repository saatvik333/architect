"""Rule-based and LLM-backed failure classifier."""

from __future__ import annotations

import json
import re
from typing import Any

from architect_common.enums import FailureCode
from architect_common.logging import get_logger
from architect_llm.client import LLMClient
from architect_llm.models import LLMRequest

from .config import FailureTaxonomyConfig
from .models import ClassificationRequest, FailureClassification

logger = get_logger(component="failure_taxonomy.classifier")

# ── Rule patterns ────────────────────────────────────────────────────

_RULE_PATTERNS: list[tuple[re.Pattern[str], FailureCode, str]] = [
    # F5: Dependency issues
    (
        re.compile(r"(?i)(ImportError|ModuleNotFoundError|No module named)"),
        FailureCode.F5_DEPENDENCY_ISSUE,
        "Missing or unresolvable dependency",
    ),
    # F6: Compilation/syntax errors (must come before F4 since both can match)
    (
        re.compile(r"(?i)(SyntaxError|IndentationError|TabError|invalid syntax)"),
        FailureCode.F6_LOGIC_BUG,
        "Syntax or compilation error in generated code",
    ),
    # F4: Tool failures (non-syntax compilation errors, build tool errors)
    (
        re.compile(
            r"(?i)(CompilationError|BuildError|ToolError|command not found|subprocess.*failed)"
        ),
        FailureCode.F4_TOOL_FAILURE,
        "Build tool or external tool failure",
    ),
    # F9: Security vulnerabilities
    (
        re.compile(
            r"(?i)(security|vulnerability|CVE-|injection|XSS|CSRF|unsafe|insecure|hardcoded.*(secret|password|key))"
        ),
        FailureCode.F9_SECURITY_VULN,
        "Security vulnerability detected",
    ),
    # F8: Performance regressions
    (
        re.compile(
            r"(?i)(performance|regression|slow|timeout|latency|throughput|memory.*(leak|exceeded)|OOM)"
        ),
        FailureCode.F8_PERF_REGRESSION,
        "Performance regression or resource issue",
    ),
    # F1: Spec ambiguity/compliance
    (
        re.compile(
            r"(?i)(spec.*compliance|specification.*(?:fail|violat)|requirement.*(?:miss|unmet)|ambiguous.*spec)"
        ),
        FailureCode.F1_SPEC_AMBIGUITY,
        "Specification compliance failure or ambiguity",
    ),
    # F2: Architecture violations
    (
        re.compile(
            r"(?i)(architecture|circular.*(?:import|dependency)|layer.*violation|coupling|service.*import.*service)"
        ),
        FailureCode.F2_ARCHITECTURE_ERROR,
        "Architecture or design constraint violation",
    ),
    # F3: Hallucination (non-existent API references)
    (
        re.compile(
            r"(?i)(AttributeError.*has no attribute|NameError.*not defined|hallucin|non-?existent.*(?:api|function|method|class)|undefined.*(?:reference|symbol))"
        ),
        FailureCode.F3_HALLUCINATION,
        "Reference to non-existent API or fabricated code construct",
    ),
    # F7: UX/taste rejection
    (
        re.compile(r"(?i)(UX|user.*experience|taste|aesthetic|usability|accessibility.*fail)"),
        FailureCode.F7_UX_REJECTION,
        "UX quality or taste criteria not met",
    ),
]

# Eval layer to failure code defaults (when no pattern matches the error itself)
_LAYER_DEFAULTS: dict[str, FailureCode] = {
    "compilation": FailureCode.F6_LOGIC_BUG,
    "unit_tests": FailureCode.F6_LOGIC_BUG,
    "integration_tests": FailureCode.F6_LOGIC_BUG,
    "adversarial": FailureCode.F9_SECURITY_VULN,
    "spec_compliance": FailureCode.F1_SPEC_AMBIGUITY,
    "architecture": FailureCode.F2_ARCHITECTURE_ERROR,
    "regression": FailureCode.F8_PERF_REGRESSION,
}


class FailureClassifier:
    """Classify failures into the ARCHITECT failure taxonomy (F1-F9).

    Uses a two-stage approach:
    1. Rule-based pattern matching for high-confidence classifications.
    2. LLM fallback for ambiguous cases (when ``use_llm_classification`` is True).
    """

    def __init__(
        self,
        config: FailureTaxonomyConfig,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._config = config
        self._llm_client = llm_client

    async def classify(self, request: ClassificationRequest) -> FailureClassification:
        """Classify a failure into the taxonomy.

        Args:
            request: The failure details to classify.

        Returns:
            A :class:`FailureClassification` with code, confidence, and summary.
        """
        # Stage 1: Rule-based classification
        rule_result = self._classify_by_rules(request)
        if (
            rule_result is not None
            and rule_result.confidence >= self._config.classification_confidence_threshold
        ):
            logger.info(
                "rule-based classification",
                task_id=request.task_id,
                failure_code=rule_result.failure_code,
                confidence=rule_result.confidence,
            )
            return rule_result

        # Stage 2: LLM fallback (if enabled and client available)
        if self._config.use_llm_classification and self._llm_client is not None:
            try:
                llm_result = await self._classify_by_llm(request, rule_result)
                logger.info(
                    "llm-based classification",
                    task_id=request.task_id,
                    failure_code=llm_result.failure_code,
                    confidence=llm_result.confidence,
                )
                return llm_result
            except Exception:
                logger.warning(
                    "llm classification failed, falling back to rule result",
                    task_id=request.task_id,
                    exc_info=True,
                )

        # Fall back to rule result (even if low confidence) or a default
        if rule_result is not None:
            return rule_result

        return FailureClassification(
            failure_code=FailureCode.F6_LOGIC_BUG,
            confidence=0.3,
            summary="Unable to classify failure; defaulting to logic bug",
            root_cause=request.error_message[:500] if request.error_message else None,
        )

    def _classify_by_rules(self, request: ClassificationRequest) -> FailureClassification | None:
        """Apply rule-based patterns to the error message and stack trace."""
        text = "\n".join(
            part
            for part in [request.error_message, request.stack_trace, request.code_context]
            if part
        )
        if not text:
            # No text to match -- try eval layer default
            if request.eval_layer and request.eval_layer in _LAYER_DEFAULTS:
                code = _LAYER_DEFAULTS[request.eval_layer]
                return FailureClassification(
                    failure_code=code,
                    confidence=0.5,
                    summary=f"Classified by eval layer: {request.eval_layer}",
                )
            return None

        # Check each pattern
        for pattern, code, summary in _RULE_PATTERNS:
            match = pattern.search(text)
            if match:
                confidence = 0.85
                return FailureClassification(
                    failure_code=code,
                    confidence=confidence,
                    summary=summary,
                    root_cause=request.error_message[:500] if request.error_message else None,
                )

        # No pattern matched -- try eval layer default with lower confidence
        if request.eval_layer and request.eval_layer in _LAYER_DEFAULTS:
            code = _LAYER_DEFAULTS[request.eval_layer]
            return FailureClassification(
                failure_code=code,
                confidence=0.5,
                summary=f"No pattern match; classified by eval layer: {request.eval_layer}",
                root_cause=request.error_message[:500] if request.error_message else None,
            )

        return None

    async def _classify_by_llm(
        self,
        request: ClassificationRequest,
        rule_hint: FailureClassification | None,
    ) -> FailureClassification:
        """Use the LLM to classify an ambiguous failure."""
        assert self._llm_client is not None

        failure_codes_desc = "\n".join(f"- {code.value}: {code.name}" for code in FailureCode)

        hint_text = ""
        if rule_hint:
            hint_text = (
                f"\nRule-based hint: {rule_hint.failure_code.value} "
                f"(confidence: {rule_hint.confidence})"
            )

        system_prompt = (
            "You are a failure classification expert for the ARCHITECT autonomous coding system. "
            "Classify the given failure into exactly one failure code from the taxonomy.\n\n"
            f"Failure codes:\n{failure_codes_desc}\n\n"
            "Respond with valid JSON only, no markdown fences:\n"
            '{"failure_code": "<code>", "confidence": <0.0-1.0>, '
            '"summary": "<one-line summary>", "root_cause": "<root cause>", '
            '"suggested_fix": "<fix suggestion>"}'
        )

        user_content = (
            f"Error message: <user_input>{request.error_message}</user_input>\n"
            f"Stack trace: <user_input>{request.stack_trace or 'N/A'}</user_input>\n"
            f"Eval layer: {request.eval_layer or 'N/A'}\n"
            f"Code context: <user_input>{request.code_context or 'N/A'}</user_input>"
            f"{hint_text}"
        )

        llm_request = LLMRequest(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=500,
            temperature=0.1,
        )

        response = await self._llm_client.generate(llm_request)
        return self._parse_llm_classification(response.content)

    def _parse_llm_classification(self, content: str) -> FailureClassification:
        """Parse the LLM JSON response into a FailureClassification."""
        try:
            data: dict[str, Any] = json.loads(content.strip())
        except json.JSONDecodeError:
            # Try extracting JSON from markdown fences
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                raise

        # Resolve the failure code
        raw_code = data.get("failure_code", "f6_logic_bug")
        try:
            failure_code = FailureCode(raw_code)
        except ValueError:
            # Try matching by prefix
            for code in FailureCode:
                if code.value.startswith(raw_code.lower()[:2]):
                    failure_code = code
                    break
            else:
                failure_code = FailureCode.F6_LOGIC_BUG

        return FailureClassification(
            failure_code=failure_code,
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.6)))),
            summary=str(data.get("summary", "LLM classification")),
            root_cause=data.get("root_cause"),
            suggested_fix=data.get("suggested_fix"),
        )
