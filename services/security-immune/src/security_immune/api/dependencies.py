"""FastAPI dependency injection for the Security Immune System."""

from __future__ import annotations

from functools import lru_cache

from architect_common.dependencies import ServiceDependency
from security_immune.config import SecurityImmuneConfig
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator
from security_immune.scanners.runtime_monitor import RuntimeMonitor


@lru_cache(maxsize=1)
def get_config() -> SecurityImmuneConfig:
    """Return the cached service configuration."""
    return SecurityImmuneConfig()


_code_scanner = ServiceDependency[CodeScanner]("CodeScanner")
_dependency_auditor = ServiceDependency[DependencyAuditor]("DependencyAuditor")
_prompt_validator = ServiceDependency[PromptValidator]("PromptValidator")
_runtime_monitor = ServiceDependency[RuntimeMonitor]("RuntimeMonitor")
_policy_enforcer = ServiceDependency[PolicyEnforcer]("PolicyEnforcer")

get_code_scanner = _code_scanner.get
set_code_scanner = _code_scanner.set
get_dependency_auditor = _dependency_auditor.get
set_dependency_auditor = _dependency_auditor.set
get_prompt_validator = _prompt_validator.get
set_prompt_validator = _prompt_validator.set
get_runtime_monitor = _runtime_monitor.get
set_runtime_monitor = _runtime_monitor.set
get_policy_enforcer = _policy_enforcer.get
set_policy_enforcer = _policy_enforcer.set


async def cleanup() -> None:
    """Close shared resources on shutdown."""
    await _code_scanner.cleanup()
    await _dependency_auditor.cleanup()
    await _prompt_validator.cleanup()
    await _runtime_monitor.cleanup()
    await _policy_enforcer.cleanup()
