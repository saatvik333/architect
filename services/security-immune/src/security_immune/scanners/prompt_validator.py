"""Prompt validator — detects injection attacks and validates output schemas."""

from __future__ import annotations

import re
import time

from pydantic import BaseModel, ValidationError

from architect_common.enums import FindingSeverity, FindingStatus, ScanType, ScanVerdict
from architect_common.logging import get_logger
from architect_common.types import new_security_finding_id, new_security_scan_id
from security_immune.models import SecurityFinding, SecurityScanResult

logger = get_logger(component="security_immune.scanners.prompt_validator")

# Prompt injection detection patterns.
_INJECTION_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "system_prompt_override",
        "Attempt to override system prompt",
        re.compile(
            r"(?i)(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
        ),
    ),
    (
        "role_hijacking",
        "Attempt to reassign the assistant role",
        re.compile(
            r"(?i)you\s+are\s+(?:now|actually)\s+(?:a|an|the)\s+",
        ),
    ),
    (
        "delimiter_escape",
        "Attempt to break out of delimiters",
        re.compile(
            r"</(?:user_input|system|assistant|human)>",
        ),
    ),
    (
        "instruction_injection",
        "Embedded system-level instruction",
        re.compile(
            r"(?i)\[(?:system|admin|root)\]\s*:",
        ),
    ),
    (
        "encoding_evasion",
        "Base64 or hex encoded payload",
        re.compile(
            r"(?i)(?:base64|hex)\s*(?:decode|encode)\s*[\(\[]",
        ),
    ),
    (
        "prompt_leak_request",
        "Attempt to extract system prompt",
        re.compile(
            r"(?i)(?:repeat|show|print|reveal|output)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions|rules)",
        ),
    ),
    (
        "jailbreak_pattern",
        "Common jailbreak technique detected",
        re.compile(
            r"(?i)(?:DAN|developer\s+mode|do\s+anything\s+now|act\s+as\s+if)",
        ),
    ),
]


class PromptValidator:
    """Validates LLM inputs and outputs for injection attacks and schema compliance."""

    def validate_input(self, text: str) -> SecurityScanResult:
        """Scan user input text for prompt injection patterns.

        Args:
            text: The user input text to validate.

        Returns:
            A :class:`SecurityScanResult` with any injection findings.
        """
        scan_id = new_security_scan_id()
        start = time.monotonic()
        findings: list[SecurityFinding] = []

        for category, description, pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.HIGH,
                        category=f"prompt_injection.{category}",
                        title=description,
                        description=(
                            f"Detected prompt injection pattern '{category}' "
                            f"in input text near: '{match.group()[:50]}'"
                        ),
                        location="user_input",
                        remediation="Sanitise user input or wrap in delimiter tags.",
                        cwe_id="CWE-77",
                        status=FindingStatus.OPEN,
                    )
                )

        duration_ms = int((time.monotonic() - start) * 1000)
        verdict = ScanVerdict.FAIL if findings else ScanVerdict.PASS

        logger.info(
            "prompt input validation complete",
            scan_id=scan_id,
            findings=len(findings),
            verdict=verdict,
        )

        return SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.PROMPT_INJECTION,
            target="user_input",
            verdict=verdict,
            findings=findings,
            duration_ms=duration_ms,
        )

    def validate_output(
        self,
        text: str,
        expected_schema: type[BaseModel] | None = None,
    ) -> SecurityScanResult:
        """Validate LLM output against an expected Pydantic schema.

        Args:
            text: The raw LLM output text.
            expected_schema: An optional Pydantic model class to validate against.

        Returns:
            A :class:`SecurityScanResult` with schema validation findings.
        """
        scan_id = new_security_scan_id()
        start = time.monotonic()
        findings: list[SecurityFinding] = []

        if expected_schema is not None:
            try:
                expected_schema.model_validate_json(text)
            except ValidationError as exc:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.MEDIUM,
                        category="schema_violation",
                        title="LLM output does not match expected schema",
                        description=(
                            f"Validation failed with {exc.error_count()} error(s): "
                            f"{exc.errors()[0]['msg'] if exc.errors() else 'unknown'}"
                        ),
                        location="llm_output",
                        remediation="Retry the LLM call or adjust the prompt to enforce schema.",
                        status=FindingStatus.OPEN,
                    )
                )
            except Exception:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.MEDIUM,
                        category="schema_violation",
                        title="LLM output could not be parsed as JSON",
                        description="The output is not valid JSON.",
                        location="llm_output",
                        remediation="Ensure the LLM prompt requests JSON output.",
                        status=FindingStatus.OPEN,
                    )
                )

        # Also check for injection patterns in output (LLM may have been compromised).
        for category, description, pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.MEDIUM,
                        category=f"output_injection.{category}",
                        title=f"Suspicious pattern in LLM output: {description}",
                        description=(
                            f"Detected pattern '{category}' in LLM output "
                            f"near: '{match.group()[:50]}'"
                        ),
                        location="llm_output",
                        remediation="Review the LLM output for prompt leakage or injection.",
                        status=FindingStatus.OPEN,
                    )
                )

        duration_ms = int((time.monotonic() - start) * 1000)
        verdict = self._compute_verdict(findings)

        logger.info(
            "prompt output validation complete",
            scan_id=scan_id,
            findings=len(findings),
            verdict=verdict,
        )

        return SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.PROMPT_INJECTION,
            target="llm_output",
            verdict=verdict,
            findings=findings,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _compute_verdict(findings: list[SecurityFinding]) -> ScanVerdict:
        """Derive the overall scan verdict from findings."""
        if not findings:
            return ScanVerdict.PASS
        severities = {f.severity for f in findings}
        if FindingSeverity.CRITICAL in severities or FindingSeverity.HIGH in severities:
            return ScanVerdict.FAIL
        if FindingSeverity.MEDIUM in severities:
            return ScanVerdict.WARN
        return ScanVerdict.PASS
