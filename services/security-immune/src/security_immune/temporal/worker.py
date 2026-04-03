"""Temporal worker entry point for the Security Immune System."""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from architect_common.logging import get_logger, setup_logging
from security_immune.config import SecurityImmuneConfig
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator
from security_immune.scanners.runtime_monitor import RuntimeMonitor
from security_immune.temporal.activities import SecurityActivities
from security_immune.temporal.workflows import (
    DependencyAuditWorkflow,
    SecurityMonitoringWorkflow,
    SecurityScanWorkflow,
)

logger = get_logger(component="security_immune.temporal.worker")


async def run_worker(
    config: SecurityImmuneConfig | None = None,
    code_scanner: CodeScanner | None = None,
    dependency_auditor: DependencyAuditor | None = None,
    prompt_validator: PromptValidator | None = None,
    runtime_monitor: RuntimeMonitor | None = None,
    policy_enforcer: PolicyEnforcer | None = None,
) -> None:
    """Connect to Temporal and start the security immune system worker.

    When called from :func:`main` (standalone mode), fresh instances are
    created.  When called from the FastAPI lifespan, the *shared* singletons
    are passed in so that Temporal activities and the REST API see the same
    state.
    """
    if config is None:
        config = SecurityImmuneConfig()
    setup_logging(log_level=config.log_level)

    if code_scanner is None:
        code_scanner = CodeScanner(config)
    if dependency_auditor is None:
        dependency_auditor = DependencyAuditor(config)
    if prompt_validator is None:
        prompt_validator = PromptValidator()
    if runtime_monitor is None:
        runtime_monitor = RuntimeMonitor()
    if policy_enforcer is None:
        policy_enforcer = PolicyEnforcer(config)

    logger.info(
        "connecting to temporal",
        target=config.architect.temporal.target,
        namespace=config.architect.temporal.namespace,
        task_queue=config.temporal_task_queue,
    )

    client = await Client.connect(
        config.architect.temporal.target,
        namespace=config.architect.temporal.namespace,
    )

    security_activities = SecurityActivities(
        config=config,
        code_scanner=code_scanner,
        dependency_auditor=dependency_auditor,
        prompt_validator=prompt_validator,
        runtime_monitor=runtime_monitor,
        policy_enforcer=policy_enforcer,
    )

    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        activities=[
            security_activities.scan_code,
            security_activities.audit_dependencies,
            security_activities.validate_prompt,
            security_activities.analyze_runtime,
            security_activities.evaluate_gate,
        ],
        workflows=[
            SecurityScanWorkflow,
            DependencyAuditWorkflow,
            SecurityMonitoringWorkflow,
        ],
    )

    logger.info("security-immune worker started", task_queue=config.temporal_task_queue)
    await worker.run()


def main() -> None:
    """CLI entry point for ``python -m security_immune.temporal.worker``."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
