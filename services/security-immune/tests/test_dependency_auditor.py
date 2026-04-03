"""Tests for the DependencyAuditor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from architect_common.enums import FindingSeverity, ScanVerdict
from security_immune.config import SecurityImmuneConfig
from security_immune.models import PackageSpec
from security_immune.scanners.dependency_auditor import DependencyAuditor, _levenshtein_distance


class TestLevenshteinDistance:
    """Unit tests for the Levenshtein distance helper."""

    def test_identical_strings(self) -> None:
        assert _levenshtein_distance("hello", "hello") == 0

    def test_single_insertion(self) -> None:
        assert _levenshtein_distance("hello", "helllo") == 1

    def test_single_deletion(self) -> None:
        assert _levenshtein_distance("hello", "helo") == 1

    def test_single_substitution(self) -> None:
        assert _levenshtein_distance("hello", "hallo") == 1

    def test_empty_strings(self) -> None:
        assert _levenshtein_distance("", "") == 0

    def test_one_empty(self) -> None:
        assert _levenshtein_distance("abc", "") == 3


class TestDependencyAuditor:
    """Unit tests for dependency auditing."""

    async def test_clean_packages_pass(self, config: SecurityImmuneConfig) -> None:
        """Well-known pinned packages should pass."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vulns": []}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages([PackageSpec(name="requests", version="2.31.0")])
        assert result.verdict == ScanVerdict.PASS

    async def test_vulnerability_detected(self, config: SecurityImmuneConfig) -> None:
        """A package with known vulnerabilities should produce findings."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "vulns": [
                {
                    "id": "GHSA-test-vuln",
                    "summary": "Test vulnerability in testpkg",
                    "severity": [{"score": "9.1"}],
                    "affected": [
                        {
                            "ranges": [
                                {
                                    "events": [{"fixed": "2.0.0"}],
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages([PackageSpec(name="testpkg", version="1.0.0")])
        assert result.verdict == ScanVerdict.FAIL
        vuln_findings = [f for f in result.findings if f.category == "vulnerability"]
        assert len(vuln_findings) >= 1
        assert vuln_findings[0].severity == FindingSeverity.CRITICAL
        assert vuln_findings[0].remediation is not None
        assert "2.0.0" in vuln_findings[0].remediation

    async def test_osv_api_failure_handled(self, config: SecurityImmuneConfig) -> None:
        """OSV API failures should be handled gracefully."""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages([PackageSpec(name="requests", version="2.31.0")])
        # Should not crash; just skip the vuln check.
        assert result.scan_type.value == "dependency_audit"

    async def test_osv_network_error(self, config: SecurityImmuneConfig) -> None:
        """Network errors should be handled gracefully."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages([PackageSpec(name="requests", version="2.31.0")])
        assert result.scan_type.value == "dependency_audit"

    async def test_typosquatting_detection(self, dependency_auditor: DependencyAuditor) -> None:
        """Packages similar to popular ones should be flagged."""
        result = await dependency_auditor.audit_packages(
            [PackageSpec(name="requets", version="1.0.0")]
        )
        typosquat = [f for f in result.findings if f.category == "typosquatting"]
        assert len(typosquat) >= 1

    async def test_typosquatting_exact_match_ok(
        self, dependency_auditor: DependencyAuditor
    ) -> None:
        """Exact matches to popular packages should NOT be flagged for typosquatting."""
        result = await dependency_auditor.audit_packages(
            [PackageSpec(name="requests", version="2.31.0")]
        )
        typosquat = [f for f in result.findings if f.category == "typosquatting"]
        assert len(typosquat) == 0

    async def test_unpinned_version_flagged(self, dependency_auditor: DependencyAuditor) -> None:
        """Unpinned versions should produce a finding."""
        result = await dependency_auditor.audit_packages([PackageSpec(name="somepkg", version="*")])
        version_findings = [f for f in result.findings if f.category == "version_pinning"]
        assert len(version_findings) >= 1

    async def test_loosely_pinned_version_flagged(
        self, dependency_auditor: DependencyAuditor
    ) -> None:
        """Range specifiers like >= should produce a finding."""
        result = await dependency_auditor.audit_packages(
            [PackageSpec(name="somepkg", version=">=1.0.0")]
        )
        version_findings = [f for f in result.findings if f.category == "version_pinning"]
        assert len(version_findings) >= 1

    async def test_exact_version_ok(self, dependency_auditor: DependencyAuditor) -> None:
        """Exact versions should not produce version pinning findings."""
        result = await dependency_auditor.audit_packages(
            [PackageSpec(name="somepkg", version="1.2.3")]
        )
        version_findings = [f for f in result.findings if f.category == "version_pinning"]
        assert len(version_findings) == 0

    async def test_multiple_packages(self, config: SecurityImmuneConfig) -> None:
        """Auditing multiple packages should check each one."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vulns": []}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages(
            [
                PackageSpec(name="requests", version="2.31.0"),
                PackageSpec(name="flask", version="3.0.0"),
                PackageSpec(name="unpinned", version="*"),
            ]
        )
        # At least the unpinned package should produce a finding.
        assert len(result.findings) >= 1

    async def test_severity_mapping(self, config: SecurityImmuneConfig) -> None:
        """Verify CVSS score to severity mapping."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "vulns": [
                {
                    "id": "LOW-VULN",
                    "summary": "Low severity vuln",
                    "severity": [{"score": "2.5"}],
                }
            ]
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        auditor = DependencyAuditor(config, http_client=mock_client)
        result = await auditor.audit_packages([PackageSpec(name="testpkg", version="1.0.0")])
        vuln_findings = [f for f in result.findings if f.category == "vulnerability"]
        assert len(vuln_findings) == 1
        assert vuln_findings[0].severity == FindingSeverity.LOW
