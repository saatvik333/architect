"""Tests for the RuntimeMonitor."""

from __future__ import annotations

from architect_common.enums import ScanVerdict
from security_immune.models import RuntimeAnomalyReport
from security_immune.scanners.runtime_monitor import RuntimeMonitor


class TestRuntimeMonitor:
    """Unit tests for runtime anomaly detection."""

    async def test_clean_activity_passes(self, runtime_monitor: RuntimeMonitor) -> None:
        """Activity within allowed bounds should produce a PASS verdict."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-clean",
            network_connections=[
                {"remote_ip": "10.0.0.1", "remote_port": 80},
                {"remote_ip": "127.0.0.1", "remote_port": 5432},
            ],
            file_accesses=[
                {"path": "/tmp/test.py", "operation": "read"},  # nosec B108
                {"path": "/workspace/src/main.py", "operation": "write"},
            ],
            processes_spawned=[
                {"binary": "python"},
                {"binary": "/usr/bin/python3"},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        assert result.verdict == ScanVerdict.PASS

    async def test_detect_external_network(self, runtime_monitor: RuntimeMonitor) -> None:
        """Connections to external IPs should be flagged."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-net",
            network_connections=[
                {"remote_ip": "8.8.8.8", "remote_port": 443},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        assert result.verdict == ScanVerdict.FAIL
        categories = {f.category for f in result.findings}
        assert "network_violation" in categories

    async def test_private_networks_allowed(self, runtime_monitor: RuntimeMonitor) -> None:
        """Private/loopback IPs should be allowed."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-private",
            network_connections=[
                {"remote_ip": "10.0.0.1", "remote_port": 80},
                {"remote_ip": "172.16.0.1", "remote_port": 443},
                {"remote_ip": "192.168.1.1", "remote_port": 8080},
                {"remote_ip": "127.0.0.1", "remote_port": 5432},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        network_findings = [f for f in result.findings if f.category == "network_violation"]
        assert len(network_findings) == 0

    async def test_ipv6_loopback_allowed(self, runtime_monitor: RuntimeMonitor) -> None:
        """IPv6 loopback should be allowed."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-ipv6",
            network_connections=[
                {"remote_ip": "::1", "remote_port": 8080},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        network_findings = [f for f in result.findings if f.category == "network_violation"]
        assert len(network_findings) == 0

    async def test_invalid_ip_handled(self, runtime_monitor: RuntimeMonitor) -> None:
        """Invalid IP addresses should produce a low-severity finding."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-invalid",
            network_connections=[
                {"remote_ip": "not-an-ip", "remote_port": 80},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        anomaly = [f for f in result.findings if f.category == "network_anomaly"]
        assert len(anomaly) >= 1

    async def test_excessive_connections_flagged(self, runtime_monitor: RuntimeMonitor) -> None:
        """More than 100 connections should be flagged."""
        connections = [{"remote_ip": "10.0.0.1", "remote_port": i} for i in range(101)]
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-flood",
            network_connections=connections,
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        anomaly = [f for f in result.findings if f.category == "network_anomaly"]
        assert len(anomaly) >= 1

    async def test_detect_file_access_violation(self, runtime_monitor: RuntimeMonitor) -> None:
        """File accesses outside allowed paths should be flagged."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-file",
            file_accesses=[
                {"path": "/etc/passwd", "operation": "read"},
                {"path": "/root/.ssh/id_rsa", "operation": "read"},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        assert result.verdict == ScanVerdict.FAIL
        file_findings = [f for f in result.findings if f.category == "file_access_violation"]
        assert len(file_findings) == 2

    async def test_allowed_file_paths(self, runtime_monitor: RuntimeMonitor) -> None:
        """File accesses within allowed paths should not be flagged."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-ok",
            file_accesses=[
                {"path": "/tmp/output.txt", "operation": "write"},  # nosec B108
                {"path": "/workspace/main.py", "operation": "read"},
                {"path": "/home/sandbox/.config", "operation": "read"},
                {"path": "/usr/lib/python3.12/os.py", "operation": "read"},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        file_findings = [f for f in result.findings if f.category == "file_access_violation"]
        assert len(file_findings) == 0

    async def test_excessive_processes_flagged(self, runtime_monitor: RuntimeMonitor) -> None:
        """Spawning more than 50 processes should be flagged."""
        processes = [{"binary": f"proc-{i}"} for i in range(51)]
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-fork",
            processes_spawned=processes,
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        process_findings = [f for f in result.findings if f.category == "process_anomaly"]
        assert len(process_findings) >= 1

    async def test_suspicious_binary_flagged(self, runtime_monitor: RuntimeMonitor) -> None:
        """Suspicious binaries like nc, nmap should be flagged."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-sus",
            processes_spawned=[
                {"binary": "nc"},
                {"binary": "/usr/bin/nmap"},
                {"binary": "curl"},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        sus_findings = [f for f in result.findings if f.category == "suspicious_process"]
        assert len(sus_findings) >= 3

    async def test_normal_binaries_ok(self, runtime_monitor: RuntimeMonitor) -> None:
        """Normal binaries like python, git should not be flagged as suspicious."""
        report = RuntimeAnomalyReport(
            sandbox_id="sandbox-normal",
            processes_spawned=[
                {"binary": "python"},
                {"binary": "git"},
                {"binary": "npm"},
            ],
        )
        result = await runtime_monitor.analyze_sandbox_activity(report)
        sus_findings = [f for f in result.findings if f.category == "suspicious_process"]
        assert len(sus_findings) == 0

    async def test_empty_report_passes(self, runtime_monitor: RuntimeMonitor) -> None:
        """An empty report should pass cleanly."""
        report = RuntimeAnomalyReport(sandbox_id="sandbox-empty")
        result = await runtime_monitor.analyze_sandbox_activity(report)
        assert result.verdict == ScanVerdict.PASS
        assert len(result.findings) == 0

    async def test_scan_result_metadata(self, runtime_monitor: RuntimeMonitor) -> None:
        """Scan results should have proper scan_id and scan_type."""
        report = RuntimeAnomalyReport(sandbox_id="sandbox-meta")
        result = await runtime_monitor.analyze_sandbox_activity(report)
        assert result.scan_id.startswith("scan-")
        assert result.scan_type.value == "runtime_anomaly"
        assert result.target == "sandbox-meta"
