"""Temporal activity definitions for the Security Immune System.

Activities are defined as methods on :class:`SecurityActivities` so that the
Temporal worker can inject shared scanner singletons.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from architect_common.logging import get_logger
from security_immune.config import SecurityImmuneConfig
from security_immune.models import (
    CodeScanInput,
    PackageSpec,
    RuntimeAnomalyReport,
)
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator
from security_immune.scanners.runtime_monitor import RuntimeMonitor

logger = get_logger(component="security_immune.temporal.activities")


class SecurityActivities:
    """Temporal activities that operate on shared Security Immune System scanners."""

    def __init__(
        self,
        config: SecurityImmuneConfig,
        code_scanner: CodeScanner,
        dependency_auditor: DependencyAuditor,
        prompt_validator: PromptValidator,
        runtime_monitor: RuntimeMonitor,
        policy_enforcer: PolicyEnforcer,
    ) -> None:
        self._config = config
        self._code_scanner = code_scanner
        self._dependency_auditor = dependency_auditor
        self._prompt_validator = prompt_validator
        self._runtime_monitor = runtime_monitor
        self._policy_enforcer = policy_enforcer

    @activity.defn
    async def scan_code(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a code security scan.

        Args:
            params: Dict with ``code``, ``file_path``, ``language``.

        Returns:
            Serialised :class:`SecurityScanResult`.
        """
        activity.logger.info("scan_code activity started")
        scan_input = CodeScanInput(
            code=params.get("code", ""),
            file_path=params.get("file_path", "unknown"),
            language=params.get("language", "python"),
        )
        result = await self._code_scanner.scan_code(scan_input)
        return result.model_dump(mode="json")

    @activity.defn
    async def audit_dependencies(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a dependency audit.

        Args:
            params: Dict with ``packages`` (list of dicts) and ``target``.

        Returns:
            Serialised :class:`SecurityScanResult`.
        """
        activity.logger.info("audit_dependencies activity started")
        raw_packages = params.get("packages", [])
        packages = [
            PackageSpec(
                name=p.get("name", ""),
                version=p.get("version", ""),
                source=p.get("source", "pypi"),
            )
            for p in raw_packages
        ]
        target = params.get("target", "unknown")
        result = await self._dependency_auditor.audit_packages(packages, target=target)
        return result.model_dump(mode="json")

    @activity.defn
    async def validate_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run prompt injection validation.

        Args:
            params: Dict with ``text`` and optional ``direction`` ("input" or "output").

        Returns:
            Serialised :class:`SecurityScanResult`.
        """
        activity.logger.info("validate_prompt activity started")
        text = params.get("text", "")
        direction = params.get("direction", "input")

        if direction == "input":
            result = self._prompt_validator.validate_input(text)
        else:
            result = self._prompt_validator.validate_output(text)

        return result.model_dump(mode="json")

    @activity.defn
    async def analyze_runtime(self, params: dict[str, Any]) -> dict[str, Any]:
        """Analyse sandbox runtime activity.

        Args:
            params: Dict matching :class:`RuntimeAnomalyReport` fields.

        Returns:
            Serialised :class:`SecurityScanResult`.
        """
        activity.logger.info("analyze_runtime activity started")
        report = RuntimeAnomalyReport(
            sandbox_id=params.get("sandbox_id", "unknown"),
            network_connections=params.get("network_connections", []),
            file_accesses=params.get("file_accesses", []),
            processes_spawned=params.get("processes_spawned", []),
            duration_seconds=params.get("duration_seconds", 0.0),
        )
        result = await self._runtime_monitor.analyze_sandbox_activity(report)
        return result.model_dump(mode="json")

    @activity.defn
    async def evaluate_gate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the security gate based on scan results.

        Args:
            params: Dict with ``scan_results`` list of serialised scan results.

        Returns:
            Serialised :class:`GateDecision`.
        """
        activity.logger.info("evaluate_gate activity started")
        from security_immune.models import SecurityScanResult

        raw_results = params.get("scan_results", [])
        scan_results = [SecurityScanResult.model_validate(r) for r in raw_results]
        decision = await self._policy_enforcer.evaluate_gate(scan_results)
        return decision.model_dump(mode="json")
