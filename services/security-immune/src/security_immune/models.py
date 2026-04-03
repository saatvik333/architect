"""Domain models for the Security Immune System."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from architect_common.enums import (
    FindingSeverity,
    FindingStatus,
    PolicyAction,
    ScanType,
    ScanVerdict,
)
from architect_common.types import (
    ArchitectBase,
    SecurityFindingId,
    SecurityPolicyId,
    SecurityScanId,
    utcnow,
)

# ── Scan results ────────────────────────────────────────────────


class SecurityFinding(ArchitectBase):
    """A single issue found during a security scan."""

    finding_id: SecurityFindingId
    scan_id: SecurityScanId
    severity: FindingSeverity
    category: str
    title: str
    description: str
    location: str | None = None
    remediation: str | None = None
    cwe_id: str | None = None
    status: FindingStatus = FindingStatus.OPEN


class SecurityScanResult(ArchitectBase):
    """Result of a completed security scan."""

    scan_id: SecurityScanId
    scan_type: ScanType
    target: str
    verdict: ScanVerdict
    findings: list[SecurityFinding] = Field(default_factory=list)
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=utcnow)


# ── Policies ────────────────────────────────────────────────────


class SecurityPolicy(ArchitectBase):
    """A configurable security policy rule."""

    policy_id: SecurityPolicyId
    name: str
    scan_type: ScanType
    rules: dict[str, Any] = Field(default_factory=dict)
    action: PolicyAction = PolicyAction.BLOCK
    enabled: bool = True


# ── Inputs ──────────────────────────────────────────────────────


class PackageSpec(ArchitectBase):
    """Describes a single dependency package."""

    name: str
    version: str
    source: str = "pypi"


class DependencyAuditInput(ArchitectBase):
    """Input for the dependency auditor."""

    packages: list[PackageSpec]
    target: str = "unknown"


class CodeScanInput(ArchitectBase):
    """Input for the code scanner."""

    code: str
    file_path: str = "unknown"
    language: str = "python"


class PromptValidationInput(ArchitectBase):
    """Input for prompt validation."""

    text: str
    context: str = ""


class RuntimeAnomalyReport(ArchitectBase):
    """Report of sandbox runtime activity for anomaly detection."""

    sandbox_id: str
    network_connections: list[dict[str, Any]] = Field(default_factory=list)
    file_accesses: list[dict[str, Any]] = Field(default_factory=list)
    processes_spawned: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float = 0.0


# ── Gate decisions ──────────────────────────────────────────────


class GateDecision(ArchitectBase):
    """Result of the security gate evaluation."""

    allowed: bool
    action: PolicyAction
    blocking_findings: list[SecurityFinding] = Field(default_factory=list)
    scan_results: list[SecurityScanResult] = Field(default_factory=list)
