"""Policy enforcer — evaluates scan results against security gate and enforces decisions."""

from __future__ import annotations

from architect_common.enums import FindingSeverity, PolicyAction, ScanVerdict
from architect_common.logging import get_logger
from security_immune.config import SecurityImmuneConfig
from security_immune.models import GateDecision, SecurityFinding, SecurityScanResult

logger = get_logger(component="security_immune.scanners.policy_enforcer")


class PolicyEnforcer:
    """Evaluates aggregate scan results to produce a gate decision and enforce it."""

    def __init__(self, config: SecurityImmuneConfig) -> None:
        self._config = config

    async def evaluate_gate(self, scan_results: list[SecurityScanResult]) -> GateDecision:
        """Evaluate the security gate based on accumulated scan results.

        Args:
            scan_results: List of completed scan results.

        Returns:
            A :class:`GateDecision` indicating whether code may proceed.
        """
        all_findings: list[SecurityFinding] = []
        for result in scan_results:
            all_findings.extend(result.findings)

        blocking: list[SecurityFinding] = []
        for finding in all_findings:
            if finding.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH):
                blocking.append(finding)

        # Determine if any scan failed.
        any_failed = any(r.verdict == ScanVerdict.FAIL for r in scan_results)
        has_critical = any(f.severity == FindingSeverity.CRITICAL for f in all_findings)

        # Decide action.
        if has_critical and self._config.block_on_critical_vuln:
            action = PolicyAction.BLOCK
            allowed = False
        elif any_failed:
            if self._config.gate_mode == "enforce":
                action = PolicyAction.BLOCK
                allowed = False
            else:
                # Audit mode: log but allow.
                action = PolicyAction.WARN
                allowed = True
        elif blocking:
            if self._config.gate_mode == "enforce":
                action = PolicyAction.WARN
                allowed = True
            else:
                action = PolicyAction.LOG
                allowed = True
        else:
            action = PolicyAction.LOG
            allowed = True

        logger.info(
            "gate evaluation complete",
            allowed=allowed,
            action=action,
            blocking_count=len(blocking),
            total_findings=len(all_findings),
        )

        return GateDecision(
            allowed=allowed,
            action=action,
            blocking_findings=blocking,
            scan_results=scan_results,
        )

    async def enforce(self, decision: GateDecision) -> None:
        """Enforce a gate decision by logging or blocking.

        Args:
            decision: The gate decision to enforce.
        """
        if decision.action == PolicyAction.BLOCK:
            logger.warning(
                "security gate BLOCKED",
                blocking_findings=len(decision.blocking_findings),
                gate_mode=self._config.gate_mode,
            )
        elif decision.action == PolicyAction.WARN:
            logger.warning(
                "security gate WARNING",
                blocking_findings=len(decision.blocking_findings),
                gate_mode=self._config.gate_mode,
            )
        else:
            logger.info(
                "security gate passed",
                gate_mode=self._config.gate_mode,
            )
