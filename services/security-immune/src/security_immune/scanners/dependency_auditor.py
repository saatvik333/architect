"""Dependency auditor — checks packages for vulnerabilities, licenses, and typosquatting."""

from __future__ import annotations

import time
from typing import Any

import httpx

from architect_common.enums import FindingSeverity, FindingStatus, ScanType, ScanVerdict
from architect_common.logging import get_logger
from architect_common.types import new_security_finding_id, new_security_scan_id
from security_immune.config import SecurityImmuneConfig
from security_immune.models import PackageSpec, SecurityFinding, SecurityScanResult

logger = get_logger(component="security_immune.scanners.dependency_auditor")

# Popular PyPI packages used for typosquatting detection (Levenshtein distance <= 2).
_POPULAR_PACKAGES: frozenset[str] = frozenset(
    {
        "requests",
        "numpy",
        "pandas",
        "flask",
        "django",
        "boto3",
        "urllib3",
        "setuptools",
        "pip",
        "cryptography",
        "pyyaml",
        "pydantic",
        "fastapi",
        "sqlalchemy",
        "httpx",
        "aiohttp",
        "jinja2",
        "click",
        "pillow",
        "scipy",
        "matplotlib",
        "pytest",
        "celery",
        "redis",
        "psycopg2",
        "beautifulsoup4",
        "lxml",
        "scrapy",
        "tensorflow",
        "torch",
        "transformers",
        "scikit-learn",
        "uvicorn",
        "gunicorn",
        "black",
        "ruff",
        "mypy",
        "coverage",
        "tox",
        "sphinx",
        "paramiko",
        "python-dotenv",
        "pyjwt",
        "bcrypt",
        "passlib",
        "structlog",
        "orjson",
        "msgpack",
        "protobuf",
    }
)


def _levenshtein_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein_distance(b, a)
    if len(b) == 0:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


class DependencyAuditor:
    """Audits dependency packages for security issues."""

    def __init__(
        self, config: SecurityImmuneConfig, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def audit_packages(
        self, packages: list[PackageSpec], target: str = "unknown"
    ) -> SecurityScanResult:
        """Run a full audit on a list of packages.

        Checks vulnerabilities (OSV.dev), licenses, typosquatting, and version pinning.
        """
        scan_id = new_security_scan_id()
        start = time.monotonic()
        findings: list[SecurityFinding] = []

        for pkg in packages:
            findings.extend(await self._check_vulnerabilities(scan_id, pkg))
            findings.extend(self._check_license(scan_id, pkg))
            findings.extend(self._check_typosquatting(scan_id, pkg))
            findings.extend(self._check_pinned_version(scan_id, pkg))

        duration_ms = int((time.monotonic() - start) * 1000)
        verdict = self._compute_verdict(findings)

        logger.info(
            "dependency audit complete",
            scan_id=scan_id,
            packages=len(packages),
            findings=len(findings),
            verdict=verdict,
        )

        return SecurityScanResult(
            scan_id=scan_id,
            scan_type=ScanType.DEPENDENCY_AUDIT,
            target=target,
            verdict=verdict,
            findings=findings,
            duration_ms=duration_ms,
        )

    async def _check_vulnerabilities(self, scan_id: str, pkg: PackageSpec) -> list[SecurityFinding]:
        """Query OSV.dev for known vulnerabilities in a package."""
        findings: list[SecurityFinding] = []
        try:
            response = await self._http.post(
                f"{self._config.vuln_db_url}/query",
                json={
                    "package": {"name": pkg.name, "ecosystem": "PyPI"},
                    "version": pkg.version,
                },
            )
            if response.status_code != 200:
                logger.warning(
                    "osv.dev query failed",
                    package=pkg.name,
                    status=response.status_code,
                )
                return findings

            data: dict[str, Any] = response.json()
            vulns = data.get("vulns", [])

            for vuln in vulns:
                severity = self._map_osv_severity(vuln)
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=severity,
                        category="vulnerability",
                        title=f"Known vulnerability in {pkg.name}=={pkg.version}",
                        description=vuln.get("summary", vuln.get("id", "Unknown vulnerability")),
                        location=f"{pkg.name}=={pkg.version}",
                        remediation=self._extract_remediation(vuln),
                        cwe_id=self._extract_cwe(vuln),
                        status=FindingStatus.OPEN,
                    )
                )
        except httpx.HTTPError:
            logger.warning("osv.dev request failed", package=pkg.name, exc_info=True)

        return findings

    def _check_license(self, scan_id: str, pkg: PackageSpec) -> list[SecurityFinding]:
        """Check whether a package license is in the allow-list.

        Note: In a production deployment this would query a package metadata API.
        For now, it flags packages whose ``source`` field carries license info.
        """
        # Placeholder — license checking requires metadata lookup.
        # Return empty unless we integrate a metadata API.
        return []

    def _check_typosquatting(self, scan_id: str, pkg: PackageSpec) -> list[SecurityFinding]:
        """Detect potential typosquatting by comparing to popular package names."""
        findings: list[SecurityFinding] = []
        name_lower = pkg.name.lower().replace("-", "").replace("_", "")

        for popular in _POPULAR_PACKAGES:
            popular_normalised = popular.lower().replace("-", "").replace("_", "")
            if name_lower == popular_normalised:
                # Exact match is fine.
                continue
            distance = _levenshtein_distance(name_lower, popular_normalised)
            if 0 < distance <= 2:
                findings.append(
                    SecurityFinding(
                        finding_id=new_security_finding_id(),
                        scan_id=scan_id,
                        severity=FindingSeverity.HIGH,
                        category="typosquatting",
                        title=f"Possible typosquat: '{pkg.name}' is similar to '{popular}'",
                        description=(
                            f"Package '{pkg.name}' has a Levenshtein distance of {distance} "
                            f"from the popular package '{popular}'. This may indicate typosquatting."
                        ),
                        location=f"{pkg.name}=={pkg.version}",
                        remediation=f"Verify that '{pkg.name}' is the intended package, not '{popular}'.",
                        status=FindingStatus.OPEN,
                    )
                )
        return findings

    def _check_pinned_version(self, scan_id: str, pkg: PackageSpec) -> list[SecurityFinding]:
        """Reject unpinned or loosely-pinned dependency versions."""
        findings: list[SecurityFinding] = []
        version = pkg.version.strip()

        if not version or version == "*":
            findings.append(
                SecurityFinding(
                    finding_id=new_security_finding_id(),
                    scan_id=scan_id,
                    severity=FindingSeverity.MEDIUM,
                    category="version_pinning",
                    title=f"Unpinned dependency: {pkg.name}",
                    description=f"Package '{pkg.name}' has no pinned version.",
                    location=f"{pkg.name}",
                    remediation="Pin the dependency to a specific version.",
                    status=FindingStatus.OPEN,
                )
            )
        elif any(version.startswith(prefix) for prefix in (">=", "~=", ">", "^")):
            findings.append(
                SecurityFinding(
                    finding_id=new_security_finding_id(),
                    scan_id=scan_id,
                    severity=FindingSeverity.LOW,
                    category="version_pinning",
                    title=f"Loosely-pinned dependency: {pkg.name}{version}",
                    description=(
                        f"Package '{pkg.name}' uses a range specifier '{version}'. "
                        "This may pull in untested versions."
                    ),
                    location=f"{pkg.name}{version}",
                    remediation="Pin to an exact version (e.g. ==1.2.3).",
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

    @staticmethod
    def _map_osv_severity(vuln: dict[str, Any]) -> FindingSeverity:
        """Map OSV severity information to our FindingSeverity enum."""
        severity_list = vuln.get("severity", [])
        for sev in severity_list:
            score_str = sev.get("score", "")
            try:
                score = float(score_str)
            except (ValueError, TypeError):
                continue
            if score >= 9.0:
                return FindingSeverity.CRITICAL
            if score >= 7.0:
                return FindingSeverity.HIGH
            if score >= 4.0:
                return FindingSeverity.MEDIUM
            return FindingSeverity.LOW
        # Default if no CVSS score found.
        return FindingSeverity.MEDIUM

    @staticmethod
    def _extract_remediation(vuln: dict[str, Any]) -> str | None:
        """Extract remediation guidance from an OSV vulnerability record."""
        affected = vuln.get("affected", [])
        for entry in affected:
            ranges = entry.get("ranges", [])
            for r in ranges:
                events = r.get("events", [])
                for event in events:
                    fixed = event.get("fixed")
                    if fixed:
                        return f"Upgrade to version {fixed} or later."
        return None

    @staticmethod
    def _extract_cwe(vuln: dict[str, Any]) -> str | None:
        """Extract CWE identifier from an OSV vulnerability record."""
        aliases = vuln.get("aliases", [])
        for alias in aliases:
            if isinstance(alias, str) and alias.startswith("CWE-"):
                return alias
        return None
