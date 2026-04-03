"""Runtime monitor — analyses sandbox activity for anomalies."""

from __future__ import annotations

import ipaddress
import time

from architect_common.enums import FindingSeverity, FindingStatus, ScanType, ScanVerdict
from architect_common.logging import get_logger
from architect_common.types import new_security_finding_id, new_security_scan_id
from security_immune.models import RuntimeAnomalyReport, SecurityFinding, SecurityScanResult

logger = get_logger(component="security_immune.scanners.runtime_monitor")

# Private/loopback CIDRs that sandbox code is allowed to contact.
_ALLOWED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]

# File path prefixes that sandbox code is allowed to access.
_ALLOWED_FILE_PREFIXES: tuple[str, ...] = (
    "/tmp/",
    "/workspace/",
    "/home/sandbox/",
    "/usr/lib/",
    "/usr/local/lib/",
)

# Maximum processes a sandbox should spawn.
_MAX_PROCESSES = 50

# Maximum network connections.
_MAX_NETWORK_CONNECTIONS = 100


class RuntimeMonitor:
    """Monitors sandbox runtime activity and flags anomalies."""

    async def analyze_sandbox_activity(self, report: RuntimeAnomalyReport) -> SecurityScanResult:
        """Analyse a sandbox activity report for anomalies.

        Args:
            report: Runtime activity collected from a sandbox session.

        Returns:
            A :class:`SecurityScanResult` with anomaly findings.
        """
        scan_id = new_security_scan_id()
        start = time.monotonic()
        findings: list[SecurityFinding] = []

        findings.extend(self._check_network_violations(scan_id, report))
        findings.extend(self._check_file_access_violations(scan_id, report))
        findings.extend(self._check_process_violations(scan_id, report))

        duration_ms = int((time.monotonic() - start) * 1000)
        verdict = self._compute_verdict(findings)

        logger.info(
            "runtime analysis complete",
            scan_id=scan_id,
            sandbox_id=report.sandbox_id,
            findings=len(findings),
            verdict=verdict,
        )

        return SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.RUNTIME_ANOMALY,
            target=report.sandbox_id,
            verdict=verdict,
            findings=findings,
            duration_ms=duration_ms,
        )

    def _check_network_violations(
        self, scan_id: str, report: RuntimeAnomalyReport
    ) -> list[SecurityFinding]:
        """Check for connections to disallowed network addresses."""
        findings: list[SecurityFinding] = []

        # Threshold check: too many connections.
        if len(report.network_connections) > _MAX_NETWORK_CONNECTIONS:
            findings.append(
                SecurityFinding(
                    finding_id=new_security_finding_id(),
                    scan_id=scan_id,
                    severity=FindingSeverity.HIGH,
                    category="network_anomaly",
                    title="Excessive network connections",
                    description=(
                        f"Sandbox '{report.sandbox_id}' made "
                        f"{len(report.network_connections)} network connections "
                        f"(threshold: {_MAX_NETWORK_CONNECTIONS})."
                    ),
                    location=report.sandbox_id,
                    remediation="Investigate why the sandbox needs so many connections.",
                    status=FindingStatus.OPEN,
                )
            )

        for conn in report.network_connections:
            remote_ip = conn.get("remote_ip", "")
            if not remote_ip:
                continue
            try:
                addr = ipaddress.ip_address(remote_ip)
            except ValueError:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.LOW,
                        category="network_anomaly",
                        title=f"Invalid IP address: {remote_ip}",
                        description=f"Could not parse '{remote_ip}' as an IP address.",
                        location=report.sandbox_id,
                        status=FindingStatus.OPEN,
                    )
                )
                continue

            # Check if the address falls in an allowed network.
            allowed = any(addr in network for network in _ALLOWED_NETWORKS)
            if not allowed:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.HIGH,
                        category="network_violation",
                        title=f"Disallowed network connection to {remote_ip}",
                        description=(
                            f"Sandbox '{report.sandbox_id}' connected to "
                            f"external address {remote_ip}:{conn.get('remote_port', '?')}. "
                            "Only private/loopback addresses are permitted."
                        ),
                        location=report.sandbox_id,
                        remediation="Block external network access or whitelist the address.",
                        cwe_id="CWE-918",
                        status=FindingStatus.OPEN,
                    )
                )

        return findings

    def _check_file_access_violations(
        self, scan_id: str, report: RuntimeAnomalyReport
    ) -> list[SecurityFinding]:
        """Check for file accesses outside allowed paths."""
        findings: list[SecurityFinding] = []

        for access in report.file_accesses:
            path = access.get("path", "")
            if not path:
                continue
            if not path.startswith(_ALLOWED_FILE_PREFIXES):
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.HIGH,
                        category="file_access_violation",
                        title=f"Disallowed file access: {path}",
                        description=(
                            f"Sandbox '{report.sandbox_id}' accessed "
                            f"'{path}' ({access.get('operation', 'unknown')}). "
                            "This path is outside the allowed sandbox directories."
                        ),
                        location=report.sandbox_id,
                        remediation="Restrict file system access to allowed paths only.",
                        cwe_id="CWE-22",
                        status=FindingStatus.OPEN,
                    )
                )

        return findings

    def _check_process_violations(
        self, scan_id: str, report: RuntimeAnomalyReport
    ) -> list[SecurityFinding]:
        """Check for excessive process spawning."""
        findings: list[SecurityFinding] = []

        process_count = len(report.processes_spawned)
        if process_count > _MAX_PROCESSES:
            findings.append(
                SecurityFinding(
                    finding_id=new_security_finding_id(),
                    scan_id=scan_id,
                    severity=FindingSeverity.MEDIUM,
                    category="process_anomaly",
                    title="Excessive process spawning",
                    description=(
                        f"Sandbox '{report.sandbox_id}' spawned {process_count} "
                        f"processes (threshold: {_MAX_PROCESSES}). "
                        "This may indicate a fork bomb or resource abuse."
                    ),
                    location=report.sandbox_id,
                    remediation="Investigate the sandbox workload for resource abuse.",
                    cwe_id="CWE-400",
                    status=FindingStatus.OPEN,
                )
            )

        # Check for suspicious process names.
        _suspicious_binaries = {"nc", "ncat", "nmap", "curl", "wget", "ssh", "scp"}
        for proc in report.processes_spawned:
            binary = proc.get("binary", "").rsplit("/", 1)[-1]
            if binary in _suspicious_binaries:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.HIGH,
                        category="suspicious_process",
                        title=f"Suspicious process: {binary}",
                        description=(
                            f"Sandbox '{report.sandbox_id}' launched '{binary}', "
                            "which is commonly used for network reconnaissance or exfiltration."
                        ),
                        location=report.sandbox_id,
                        remediation=f"Block '{binary}' from executing in the sandbox.",
                        cwe_id="CWE-78",
                        status=FindingStatus.OPEN,
                    )
                )

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
