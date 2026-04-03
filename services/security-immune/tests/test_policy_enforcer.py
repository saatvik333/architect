"""Tests for the PolicyEnforcer."""

from __future__ import annotations

from architect_common.enums import (
    FindingSeverity,
    FindingStatus,
    PolicyAction,
    ScanType,
    ScanVerdict,
)
from architect_common.types import new_security_finding_id, new_security_scan_id
from security_immune.config import SecurityImmuneConfig
from security_immune.models import SecurityFinding, SecurityScanResult
from security_immune.scanners.policy_enforcer import PolicyEnforcer


def _make_finding(
    severity: FindingSeverity,
    scan_id: str | None = None,
) -> SecurityFinding:
    """Create a test finding with the given severity."""
    return SecurityFinding(
        finding_id=new_security_finding_id(),
        scan_id=scan_id or new_security_scan_id(),
        severity=severity,
        category="test",
        title=f"Test {severity} finding",
        description="A test finding.",
        status=FindingStatus.OPEN,
    )


def _make_scan_result(
    verdict: ScanVerdict,
    findings: list[SecurityFinding] | None = None,
) -> SecurityScanResult:
    """Create a test scan result."""
    scan_id = new_security_scan_id()
    return SecurityScanResult(
        scan_id=scan_id,
        scan_type=ScanType.CODE_SCAN,
        target="test",
        verdict=verdict,
        findings=findings or [],
    )


class TestPolicyEnforcer:
    """Unit tests for gate evaluation and enforcement."""

    async def test_pass_with_no_findings(self, policy_enforcer: PolicyEnforcer) -> None:
        """Clean scans should result in an allowed decision."""
        results = [_make_scan_result(ScanVerdict.PASS)]
        decision = await policy_enforcer.evaluate_gate(results)
        assert decision.allowed is True
        assert decision.action == PolicyAction.LOG

    async def test_block_on_critical_vuln(self, config: SecurityImmuneConfig) -> None:
        """Critical findings should block when block_on_critical_vuln is True."""
        enforcer = PolicyEnforcer(config)
        critical_finding = _make_finding(FindingSeverity.CRITICAL)
        results = [_make_scan_result(ScanVerdict.FAIL, findings=[critical_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is False
        assert decision.action == PolicyAction.BLOCK
        assert len(decision.blocking_findings) >= 1

    async def test_block_on_high_in_enforce_mode(self, config: SecurityImmuneConfig) -> None:
        """High-severity findings should block in enforce mode."""
        enforcer = PolicyEnforcer(config)
        high_finding = _make_finding(FindingSeverity.HIGH)
        results = [_make_scan_result(ScanVerdict.FAIL, findings=[high_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is False
        assert decision.action == PolicyAction.BLOCK

    async def test_audit_mode_allows_failures(self) -> None:
        """In audit mode, failures should be logged but allowed."""
        config = SecurityImmuneConfig(gate_mode="audit")
        enforcer = PolicyEnforcer(config)
        high_finding = _make_finding(FindingSeverity.HIGH)
        results = [_make_scan_result(ScanVerdict.FAIL, findings=[high_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is True
        assert decision.action == PolicyAction.WARN

    async def test_audit_mode_still_blocks_critical(self) -> None:
        """Even in audit mode, critical vulns should block if configured."""
        config = SecurityImmuneConfig(gate_mode="audit", block_on_critical_vuln=True)
        enforcer = PolicyEnforcer(config)
        critical_finding = _make_finding(FindingSeverity.CRITICAL)
        results = [_make_scan_result(ScanVerdict.FAIL, findings=[critical_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is False
        assert decision.action == PolicyAction.BLOCK

    async def test_warn_only_with_medium_findings(self, config: SecurityImmuneConfig) -> None:
        """Medium findings should result in a warning, not a block."""
        enforcer = PolicyEnforcer(config)
        medium_finding = _make_finding(FindingSeverity.MEDIUM)
        results = [_make_scan_result(ScanVerdict.WARN, findings=[medium_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is True

    async def test_low_findings_pass(self, config: SecurityImmuneConfig) -> None:
        """Low and info findings should not block or warn."""
        enforcer = PolicyEnforcer(config)
        low_finding = _make_finding(FindingSeverity.LOW)
        info_finding = _make_finding(FindingSeverity.INFO)
        results = [_make_scan_result(ScanVerdict.PASS, findings=[low_finding, info_finding])]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is True
        assert decision.action == PolicyAction.LOG

    async def test_multiple_scan_results(self, config: SecurityImmuneConfig) -> None:
        """Gate should aggregate findings from all scan results."""
        enforcer = PolicyEnforcer(config)
        critical_finding = _make_finding(FindingSeverity.CRITICAL)
        low_finding = _make_finding(FindingSeverity.LOW)
        results = [
            _make_scan_result(ScanVerdict.PASS, findings=[low_finding]),
            _make_scan_result(ScanVerdict.FAIL, findings=[critical_finding]),
        ]
        decision = await enforcer.evaluate_gate(results)
        assert decision.allowed is False
        assert len(decision.blocking_findings) >= 1

    async def test_enforce_block_logs(self, policy_enforcer: PolicyEnforcer) -> None:
        """Enforcing a BLOCK decision should not raise."""
        from security_immune.models import GateDecision

        decision = GateDecision(
            allowed=False,
            action=PolicyAction.BLOCK,
            blocking_findings=[_make_finding(FindingSeverity.CRITICAL)],
        )
        # Should not raise.
        await policy_enforcer.enforce(decision)

    async def test_enforce_log_passes_quietly(self, policy_enforcer: PolicyEnforcer) -> None:
        """Enforcing a LOG decision should pass quietly."""
        from security_immune.models import GateDecision

        decision = GateDecision(
            allowed=True,
            action=PolicyAction.LOG,
        )
        await policy_enforcer.enforce(decision)

    async def test_empty_scan_results(self, policy_enforcer: PolicyEnforcer) -> None:
        """Empty scan results should produce an allowed decision."""
        decision = await policy_enforcer.evaluate_gate([])
        assert decision.allowed is True
        assert decision.action == PolicyAction.LOG
