"""Code scanner — detects dangerous patterns, secrets, and runs bandit analysis."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
import time
from pathlib import Path

from architect_common.enums import FindingSeverity, FindingStatus, ScanType, ScanVerdict
from architect_common.logging import get_logger
from architect_common.types import new_security_finding_id, new_security_scan_id
from security_immune.config import SecurityImmuneConfig
from security_immune.models import CodeScanInput, SecurityFinding, SecurityScanResult

logger = get_logger(component="security_immune.scanners.code_scanner")

# Bandit severity mapping.
_BANDIT_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "HIGH": FindingSeverity.HIGH,
    "MEDIUM": FindingSeverity.MEDIUM,
    "LOW": FindingSeverity.LOW,
}

_BANDIT_CONFIDENCE_MAP: dict[str, FindingSeverity] = {
    "HIGH": FindingSeverity.HIGH,
    "MEDIUM": FindingSeverity.MEDIUM,
    "LOW": FindingSeverity.INFO,
}


class CodeScanner:
    """Scans source code for security issues using pattern matching and bandit."""

    def __init__(self, config: SecurityImmuneConfig) -> None:
        self._config = config
        self._blocked_patterns = config.blocked_patterns
        self._secrets_regexes = [re.compile(p) for p in config.secrets_patterns]

    async def scan_code(self, scan_input: CodeScanInput) -> SecurityScanResult:
        """Run a full code scan: dangerous patterns, secrets, and bandit.

        Args:
            scan_input: The code to scan with metadata.

        Returns:
            A :class:`SecurityScanResult` with all findings.
        """
        scan_id = new_security_scan_id()
        start = time.monotonic()
        findings: list[SecurityFinding] = []

        # Check code size limit.
        code_size_kb = len(scan_input.code.encode("utf-8")) / 1024
        if code_size_kb > self._config.max_code_size_kb:
            findings.append(
                SecurityFinding(
                    finding_id=new_security_finding_id(),
                    scan_id=scan_id,
                    severity=FindingSeverity.MEDIUM,
                    category="code_size",
                    title="Code exceeds maximum scan size",
                    description=(
                        f"Code is {code_size_kb:.1f}KB, exceeding the "
                        f"{self._config.max_code_size_kb}KB limit."
                    ),
                    location=scan_input.file_path,
                    status=FindingStatus.OPEN,
                )
            )
        else:
            findings.extend(self._detect_dangerous_patterns(scan_id, scan_input))
            findings.extend(self._detect_secrets(scan_id, scan_input))
            findings.extend(await self._run_bandit(scan_id, scan_input))

        duration_ms = int((time.monotonic() - start) * 1000)
        verdict = self._compute_verdict(findings)

        logger.info(
            "code scan complete",
            scan_id=scan_id,
            file_path=scan_input.file_path,
            findings=len(findings),
            verdict=verdict,
        )

        return SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.CODE_SCAN,
            target=scan_input.file_path,
            verdict=verdict,
            findings=findings,
            duration_ms=duration_ms,
        )

    def _detect_dangerous_patterns(
        self, scan_id: str, scan_input: CodeScanInput
    ) -> list[SecurityFinding]:
        """Search for blocked patterns in the code."""
        findings: list[SecurityFinding] = []
        lines = scan_input.code.splitlines()

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Skip comments.
            if stripped.startswith("#"):
                continue
            for pattern in self._blocked_patterns:
                if pattern in line:
                    findings.append(
                        SecurityFinding(
                            finding_id=new_security_finding_id(),
                            scan_id=scan_id,
                            severity=FindingSeverity.HIGH,
                            category="dangerous_pattern",
                            title=f"Dangerous pattern detected: {pattern}",
                            description=(
                                f"Found '{pattern}' at line {line_num} in "
                                f"'{scan_input.file_path}'. This pattern can lead "
                                "to code injection or arbitrary code execution."
                            ),
                            location=f"{scan_input.file_path}:{line_num}",
                            remediation="Replace with a safer alternative or remove the call.",
                            cwe_id="CWE-78",
                            status=FindingStatus.OPEN,
                        )
                    )
        return findings

    def _detect_secrets(self, scan_id: str, scan_input: CodeScanInput) -> list[SecurityFinding]:
        """Search for hardcoded secrets using regex patterns."""
        findings: list[SecurityFinding] = []
        lines = scan_input.code.splitlines()

        for line_num, line in enumerate(lines, start=1):
            for regex in self._secrets_regexes:
                if regex.search(line):
                    findings.append(
                        SecurityFinding(
                            finding_id=new_security_finding_id(),
                            scan_id=scan_id,
                            severity=FindingSeverity.CRITICAL,
                            category="hardcoded_secret",
                            title="Hardcoded secret detected",
                            description=(
                                f"Potential secret found at line {line_num} in "
                                f"'{scan_input.file_path}'. Hardcoded credentials "
                                "should be moved to environment variables."
                            ),
                            location=f"{scan_input.file_path}:{line_num}",
                            remediation="Move secrets to environment variables or a secrets manager.",
                            cwe_id="CWE-798",
                            status=FindingStatus.OPEN,
                        )
                    )
                    # One finding per line is enough — avoid duplicate noise.
                    break

        return findings

    async def _run_bandit(self, scan_id: str, scan_input: CodeScanInput) -> list[SecurityFinding]:
        """Run bandit static analysis on the code and parse JSON output.

        Uses asyncio.create_subprocess_exec (not shell) for safety.
        """
        if scan_input.language != "python":
            return []

        findings: list[SecurityFinding] = []
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
                tmp.write(scan_input.code)
                tmp_path = tmp.name

            # nosec B603 — bandit is invoked with fixed arguments, no user input in argv.
            proc = await asyncio.create_subprocess_exec(  # nosec B603
                "bandit",
                "-f",
                "json",
                "-q",
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._config.scan_timeout_seconds,
            )

            if stdout:
                try:
                    data = json.loads(stdout.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning("bandit produced invalid JSON output")
                    return findings

                for result in data.get("results", []):
                    severity = _BANDIT_SEVERITY_MAP.get(
                        result.get("issue_severity", "LOW"),
                        FindingSeverity.LOW,
                    )
                    findings.append(
                        SecurityFinding(
                            finding_id=new_security_finding_id(),
                            scan_id=scan_id,
                            severity=severity,
                            category="bandit",
                            title=f"[{result.get('test_id', 'B000')}] {result.get('issue_text', 'Unknown issue')}",
                            description=result.get("issue_text", ""),
                            location=f"{scan_input.file_path}:{result.get('line_number', 0)}",
                            remediation=result.get("more_info", None),
                            cwe_id=result.get("issue_cwe", {}).get("id"),
                            status=FindingStatus.OPEN,
                        )
                    )
        except FileNotFoundError:
            logger.warning("bandit not found — skipping static analysis")
        except TimeoutError:
            logger.warning("bandit timed out")
        except Exception:
            logger.warning("bandit execution failed", exc_info=True)
        finally:
            if tmp_path is not None:
                Path(tmp_path).unlink(missing_ok=True)

        return findings

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
