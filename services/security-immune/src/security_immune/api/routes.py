"""FastAPI route definitions for the Security Immune System."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from architect_common.enums import FindingStatus, HealthStatus, PolicyAction, ScanType
from architect_common.health import HealthResponse
from security_immune.models import (
    CodeScanInput,
    PackageSpec,
    SecurityFinding,
    SecurityScanResult,
)
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator

from .dependencies import (
    get_code_scanner,
    get_dependency_auditor,
    get_policy_enforcer,
    get_prompt_validator,
)

router = APIRouter()


# ── In-memory stores (production would use the DB repos) ─────────
_scan_results: dict[str, SecurityScanResult] = {}
_findings: dict[str, SecurityFinding] = {}
_policies: list[dict[str, Any]] = []


def _store_scan(result: SecurityScanResult) -> None:
    """Store a scan result and its findings in the in-memory cache."""
    _scan_results[result.scan_id] = result
    for finding in result.findings:
        _findings[finding.finding_id] = finding


# ── Request / Response schemas ───────────────────────────────────


class CodeScanRequest(BaseModel):
    """Request body for POST /api/v1/scan/code."""

    code: str
    file_path: str = "unknown"
    language: str = "python"


class DependencyScanRequest(BaseModel):
    """Request body for POST /api/v1/scan/dependencies."""

    packages: list[PackageSpec]
    target: str = "unknown"


class PromptScanRequest(BaseModel):
    """Request body for POST /api/v1/scan/prompt."""

    text: str
    context: str = ""
    direction: str = Field(default="input", pattern=r"^(input|output)$")


class UpdateFindingStatusRequest(BaseModel):
    """Request body for PATCH /api/v1/findings/{finding_id}/status."""

    status: FindingStatus


class CreatePolicyRequest(BaseModel):
    """Request body for POST /api/v1/policies."""

    name: str
    scan_type: ScanType
    rules: dict[str, Any] = Field(default_factory=dict)
    action: PolicyAction = PolicyAction.BLOCK
    enabled: bool = True


class GateStatusResponse(BaseModel):
    """Response body for GET /api/v1/gate/status."""

    mode: str
    recent_scans: int
    recent_blocked: int
    block_on_critical: bool


class StatsResponse(BaseModel):
    """Response body for GET /api/v1/stats."""

    total_scans: int
    total_findings: int
    open_findings: int
    critical_findings: int
    high_findings: int


# ── Scan endpoints ───────────────────────────────────────────────


@router.post("/api/v1/scan/code", response_model=SecurityScanResult)
async def scan_code(
    body: CodeScanRequest,
    scanner: CodeScanner = Depends(get_code_scanner),
) -> SecurityScanResult:
    """Run a code security scan."""
    scan_input = CodeScanInput(
        code=body.code,
        file_path=body.file_path,
        language=body.language,
    )
    result = await scanner.scan_code(scan_input)
    _store_scan(result)
    return result


@router.post("/api/v1/scan/dependencies", response_model=SecurityScanResult)
async def scan_dependencies(
    body: DependencyScanRequest,
    auditor: DependencyAuditor = Depends(get_dependency_auditor),
) -> SecurityScanResult:
    """Run a dependency audit scan."""
    result = await auditor.audit_packages(body.packages, target=body.target)
    _store_scan(result)
    return result


@router.post("/api/v1/scan/prompt", response_model=SecurityScanResult)
async def scan_prompt(
    body: PromptScanRequest,
    validator: PromptValidator = Depends(get_prompt_validator),
) -> SecurityScanResult:
    """Run a prompt injection scan."""
    if body.direction == "input":
        result = validator.validate_input(body.text)
    else:
        result = validator.validate_output(body.text)
    _store_scan(result)
    return result


# ── Scan result lookup ───────────────────────────────────────────


@router.get("/api/v1/scan/{scan_id}", response_model=SecurityScanResult)
async def get_scan(scan_id: str) -> SecurityScanResult:
    """Retrieve a scan result by ID."""
    result = _scan_results.get(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found")
    return result


# ── Finding endpoints ────────────────────────────────────────────


@router.get("/api/v1/findings", response_model=list[SecurityFinding])
async def list_findings(
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[SecurityFinding]:
    """List findings, optionally filtered by severity or status."""
    results = list(_findings.values())
    if severity:
        results = [f for f in results if f.severity == severity]
    if status:
        results = [f for f in results if f.status == status]
    return results[:limit]


@router.get("/api/v1/findings/{finding_id}", response_model=SecurityFinding)
async def get_finding(finding_id: str) -> SecurityFinding:
    """Retrieve a single finding by ID."""
    finding = _findings.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found")
    return finding


@router.patch("/api/v1/findings/{finding_id}/status", response_model=SecurityFinding)
async def update_finding_status(
    finding_id: str,
    body: UpdateFindingStatusRequest,
) -> SecurityFinding:
    """Update the status of a finding."""
    finding = _findings.get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found")
    # Frozen model — create a new instance with the updated status.
    updated = finding.model_copy(update={"status": body.status})
    _findings[finding_id] = updated
    return updated


# ── Policy endpoints ─────────────────────────────────────────────


@router.get("/api/v1/policies")
async def list_policies() -> list[dict[str, Any]]:
    """List all security policies."""
    return _policies


@router.post("/api/v1/policies", status_code=201)
async def create_policy(body: CreatePolicyRequest) -> dict[str, Any]:
    """Create a new security policy."""
    from architect_common.types import new_security_policy_id

    policy = {
        "policy_id": new_security_policy_id(),
        "name": body.name,
        "scan_type": body.scan_type,
        "rules": body.rules,
        "action": body.action,
        "enabled": body.enabled,
    }
    _policies.append(policy)
    return policy


# ── Gate and stats endpoints ─────────────────────────────────────


@router.get("/api/v1/gate/status", response_model=GateStatusResponse)
async def get_gate_status(
    enforcer: PolicyEnforcer = Depends(get_policy_enforcer),
) -> GateStatusResponse:
    """Return the current gate configuration and recent activity."""
    from security_immune.api.dependencies import get_config

    config = get_config()
    blocked_count = sum(1 for r in _scan_results.values() if r.verdict == "fail")
    return GateStatusResponse(
        mode=config.gate_mode,
        recent_scans=len(_scan_results),
        recent_blocked=blocked_count,
        block_on_critical=config.block_on_critical_vuln,
    )


@router.get("/api/v1/backlog", response_model=list[SecurityFinding])
async def get_backlog() -> list[SecurityFinding]:
    """Return all open findings (the security backlog)."""
    return [f for f in _findings.values() if f.status == FindingStatus.OPEN]


@router.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Return aggregate security statistics."""
    all_findings = list(_findings.values())
    return StatsResponse(
        total_scans=len(_scan_results),
        total_findings=len(all_findings),
        open_findings=sum(1 for f in all_findings if f.status == FindingStatus.OPEN),
        critical_findings=sum(1 for f in all_findings if f.severity == "critical"),
        high_findings=sum(1 for f in all_findings if f.severity == "high"),
    )


# ── Health check ─────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Service health check endpoint."""
    status = HealthStatus.HEALTHY

    try:
        get_code_scanner()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    try:
        get_dependency_auditor()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    try:
        get_policy_enforcer()
    except RuntimeError:
        status = HealthStatus.DEGRADED

    uptime = time.monotonic() - getattr(request.app.state, "started_at", time.monotonic())
    return HealthResponse(
        service="security-immune",
        status=status,
        uptime_seconds=round(uptime, 2),
    )
