"""Tests for Security Immune System domain models."""

from __future__ import annotations

import pytest

from architect_common.enums import (
    FindingSeverity,
    FindingStatus,
    PolicyAction,
    ScanType,
    ScanVerdict,
)
from architect_common.types import (
    new_security_finding_id,
    new_security_policy_id,
    new_security_scan_id,
)
from security_immune.models import (
    CodeScanInput,
    DependencyAuditInput,
    GateDecision,
    PackageSpec,
    PromptValidationInput,
    RuntimeAnomalyReport,
    SecurityFinding,
    SecurityPolicy,
    SecurityScanResult,
)


class TestModels:
    """Verify domain models are frozen and validate correctly."""

    def test_security_finding_frozen(self) -> None:
        finding = SecurityFinding(
            finding_id=new_security_finding_id(),
            scan_id=new_security_scan_id(),
            severity=FindingSeverity.HIGH,
            category="test",
            title="Test finding",
            description="A test finding.",
        )
        with pytest.raises(Exception):  # noqa: B017
            finding.severity = FindingSeverity.LOW  # type: ignore[misc]

    def test_security_finding_defaults(self) -> None:
        finding = SecurityFinding(
            finding_id=new_security_finding_id(),
            scan_id=new_security_scan_id(),
            severity=FindingSeverity.MEDIUM,
            category="test",
            title="Test",
            description="Test",
        )
        assert finding.status == FindingStatus.OPEN
        assert finding.location is None
        assert finding.remediation is None
        assert finding.cwe_id is None

    def test_security_scan_result_creation(self) -> None:
        scan_id = new_security_scan_id()
        result = SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.CODE_SCAN,
            target="test.py",
            verdict=ScanVerdict.PASS,
        )
        assert result.scan_id == scan_id
        assert result.findings == []
        assert result.duration_ms == 0

    def test_security_scan_result_frozen(self) -> None:
        result = SecurityScanResult(
            scan_id=new_security_scan_id(),
            scan_type=ScanType.CODE_SCAN,
            target="test.py",
            verdict=ScanVerdict.PASS,
        )
        with pytest.raises(Exception):  # noqa: B017
            result.verdict = ScanVerdict.FAIL  # type: ignore[misc]

    def test_security_policy_creation(self) -> None:
        policy = SecurityPolicy(
            policy_id=new_security_policy_id(),
            name="no-critical-vulns",
            scan_type=ScanType.DEPENDENCY_AUDIT,
            rules={"max_severity": "high"},
            action=PolicyAction.BLOCK,
        )
        assert policy.enabled is True
        assert policy.action == PolicyAction.BLOCK

    def test_package_spec(self) -> None:
        pkg = PackageSpec(name="requests", version="2.31.0")
        assert pkg.source == "pypi"

    def test_dependency_audit_input(self) -> None:
        inp = DependencyAuditInput(
            packages=[
                PackageSpec(name="requests", version="2.31.0"),
                PackageSpec(name="flask", version="3.0.0"),
            ]
        )
        assert len(inp.packages) == 2
        assert inp.target == "unknown"

    def test_code_scan_input(self) -> None:
        inp = CodeScanInput(code="print('hello')", file_path="hello.py")
        assert inp.language == "python"

    def test_prompt_validation_input(self) -> None:
        inp = PromptValidationInput(text="Hello world")
        assert inp.context == ""

    def test_runtime_anomaly_report(self) -> None:
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-123",
            network_connections=[{"remote_ip": "10.0.0.1", "remote_port": 80}],
            processes_spawned=[{"binary": "python"}],
        )
        assert report.sandbox_id == "sandbox-123"
        assert len(report.network_connections) == 1
        assert report.file_accesses == []

    def test_gate_decision_allowed(self) -> None:
        decision = GateDecision(
            allowed=True,
            action=PolicyAction.LOG,
        )
        assert decision.allowed is True
        assert decision.blocking_findings == []
        assert decision.scan_results == []

    def test_gate_decision_blocked(self) -> None:
        finding = SecurityFinding(
            finding_id=new_security_finding_id(),
            scan_id=new_security_scan_id(),
            severity=FindingSeverity.CRITICAL,
            category="vulnerability",
            title="Critical vuln",
            description="A critical vulnerability.",
        )
        decision = GateDecision(
            allowed=False,
            action=PolicyAction.BLOCK,
            blocking_findings=[finding],
        )
        assert decision.allowed is False
        assert len(decision.blocking_findings) == 1
