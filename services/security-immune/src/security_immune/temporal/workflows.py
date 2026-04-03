"""Temporal workflow definitions for the Security Immune System."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from architect_common.enums import ScanVerdict


TASK_QUEUE = "security-immune"

# Activity name constants — these correspond to methods on
# ``security_immune.temporal.activities.SecurityActivities``.
ACT_SCAN_CODE = "scan_code"
ACT_AUDIT_DEPENDENCIES = "audit_dependencies"
ACT_VALIDATE_PROMPT = "validate_prompt"
ACT_ANALYZE_RUNTIME = "analyze_runtime"
ACT_EVALUATE_GATE = "evaluate_gate"


# ── Typed workflow parameters ────────────────────────────────────


@dataclass
class SecurityScanParams:
    """Input parameters for the security scan workflow."""

    code: str = ""
    file_path: str = "unknown"
    language: str = "python"


@dataclass
class SecurityScanWorkflowResult:
    """Output of the security scan workflow."""

    scan_id: str = ""
    verdict: str = "pass"
    findings_count: int = 0
    gate_allowed: bool = True


@dataclass
class DependencyAuditParams:
    """Input parameters for the dependency audit workflow."""

    packages: list[dict[str, str]] | None = None
    target: str = "unknown"


@dataclass
class DependencyAuditWorkflowResult:
    """Output of the dependency audit workflow."""

    scan_id: str = ""
    verdict: str = "pass"
    findings_count: int = 0
    critical_count: int = 0


@dataclass
class SecurityMonitoringParams:
    """Input parameters for the security monitoring workflow."""

    poll_interval_seconds: int = 60
    max_iterations: int = 1000


@dataclass
class SecurityMonitoringResult:
    """Output of the security monitoring workflow."""

    iterations_completed: int = 0
    scans_performed: int = 0
    completed: bool = False


# ── Workflows ────────────────────────────────────────────────────


@workflow.defn
class SecurityScanWorkflow:
    """Workflow that orchestrates a full code security scan and gate evaluation.

    Steps: scan code -> evaluate gate -> return decision.
    """

    @workflow.run
    async def run(self, params: SecurityScanParams | dict[str, Any]) -> SecurityScanWorkflowResult:
        """Execute a security scan and gate evaluation.

        Args:
            params: Typed :class:`SecurityScanParams` or a dict for
                    backwards compatibility.

        Returns:
            :class:`SecurityScanWorkflowResult` with scan outcome.
        """
        if isinstance(params, dict):
            params = SecurityScanParams(
                **{k: v for k, v in params.items() if k in SecurityScanParams.__dataclass_fields__}
            )

        # Step 1: Run the code scan.
        scan_result: dict[str, Any] = await workflow.execute_activity(
            ACT_SCAN_CODE,
            args=[
                {
                    "code": params.code,
                    "file_path": params.file_path,
                    "language": params.language,
                }
            ],
            start_to_close_timeout=timedelta(seconds=120),
        )

        # Step 2: Evaluate the security gate.
        gate_result: dict[str, Any] = await workflow.execute_activity(
            ACT_EVALUATE_GATE,
            args=[{"scan_results": [scan_result]}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return SecurityScanWorkflowResult(
            scan_id=scan_result.get("scan_id", ""),
            verdict=scan_result.get("verdict", "pass"),
            findings_count=len(scan_result.get("findings", [])),
            gate_allowed=gate_result.get("allowed", True),
        )


@workflow.defn
class DependencyAuditWorkflow:
    """Workflow that audits a set of dependency packages.

    Steps: audit packages -> evaluate gate -> return decision.
    """

    @workflow.run
    async def run(
        self, params: DependencyAuditParams | dict[str, Any]
    ) -> DependencyAuditWorkflowResult:
        """Execute a dependency audit.

        Args:
            params: Typed :class:`DependencyAuditParams` or a dict for
                    backwards compatibility.

        Returns:
            :class:`DependencyAuditWorkflowResult` with audit outcome.
        """
        if isinstance(params, dict):
            params = DependencyAuditParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in DependencyAuditParams.__dataclass_fields__
                }
            )

        packages = params.packages or []

        audit_result: dict[str, Any] = await workflow.execute_activity(
            ACT_AUDIT_DEPENDENCIES,
            args=[{"packages": packages, "target": params.target}],
            start_to_close_timeout=timedelta(seconds=120),
        )

        findings = audit_result.get("findings", [])
        critical_count = sum(1 for f in findings if f.get("severity") == "critical")

        return DependencyAuditWorkflowResult(
            scan_id=audit_result.get("scan_id", ""),
            verdict=audit_result.get("verdict", "pass"),
            findings_count=len(findings),
            critical_count=critical_count,
        )


@workflow.defn
class SecurityMonitoringWorkflow:
    """Long-running periodic workflow that runs security scans at intervals.

    Used for continuous monitoring of sandbox runtime activity.
    """

    @workflow.run
    async def run(
        self, params: SecurityMonitoringParams | dict[str, Any]
    ) -> SecurityMonitoringResult:
        """Execute the security monitoring loop.

        Args:
            params: Typed :class:`SecurityMonitoringParams` or a dict for
                    backwards compatibility.

        Returns:
            :class:`SecurityMonitoringResult` with iteration count and stats.
        """
        if isinstance(params, dict):
            params = SecurityMonitoringParams(
                **{
                    k: v
                    for k, v in params.items()
                    if k in SecurityMonitoringParams.__dataclass_fields__
                }
            )

        iterations = 0
        scans_performed = 0

        while iterations < params.max_iterations:
            iterations += 1

            # Analyse runtime activity (stub — in production this would
            # fetch actual sandbox reports).
            try:
                result: dict[str, Any] = await workflow.execute_activity(
                    ACT_ANALYZE_RUNTIME,
                    args=[
                        {
                            "sandbox_id": "monitoring",
                            "network_connections": [],
                            "file_accesses": [],
                            "processes_spawned": [],
                        }
                    ],
                    start_to_close_timeout=timedelta(seconds=60),
                )
                scans_performed += 1

                verdict = result.get("verdict", "pass")
                if verdict == ScanVerdict.FAIL:
                    workflow.logger.warning(
                        "Security monitoring detected anomalies",
                        extra={"findings": len(result.get("findings", []))},
                    )
            except Exception:
                workflow.logger.warning("Security monitoring scan failed")

            await workflow.sleep(timedelta(seconds=params.poll_interval_seconds))

        return SecurityMonitoringResult(
            iterations_completed=iterations,
            scans_performed=scans_performed,
            completed=iterations >= params.max_iterations,
        )
