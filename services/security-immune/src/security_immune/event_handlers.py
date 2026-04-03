"""Event subscription handlers for the Security Immune System.

Listens for proposal, sandbox, and agent events to trigger security scans
and policy enforcement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from architect_common.logging import get_logger

if TYPE_CHECKING:
    from architect_events.schemas import EventEnvelope
    from security_immune.scanners.code_scanner import CodeScanner
    from security_immune.scanners.policy_enforcer import PolicyEnforcer
    from security_immune.scanners.runtime_monitor import RuntimeMonitor

logger = get_logger(component="security_immune.event_handlers")


async def handle_proposal_created(
    envelope: EventEnvelope,
    code_scanner: CodeScanner,
    policy_enforcer: PolicyEnforcer,
) -> None:
    """Handle PROPOSAL_CREATED events by scanning proposed code changes.

    Args:
        envelope: The incoming event from the event bus.
        code_scanner: The code scanner instance.
        policy_enforcer: The policy enforcer instance.
    """
    logger.info(
        "handling proposal_created event",
        event_type=envelope.type,
        event_id=envelope.id,
        correlation_id=envelope.correlation_id,
    )
    payload = envelope.payload or {}
    code = payload.get("diff", payload.get("code", ""))
    file_path = payload.get("file_path", "proposal")

    if code:
        from security_immune.models import CodeScanInput

        scan_input = CodeScanInput(code=code, file_path=file_path)
        result = await code_scanner.scan_code(scan_input)
        decision = await policy_enforcer.evaluate_gate([result])
        await policy_enforcer.enforce(decision)


async def handle_proposal_accepted(
    envelope: EventEnvelope,
    code_scanner: CodeScanner,
    policy_enforcer: PolicyEnforcer,
) -> None:
    """Handle PROPOSAL_ACCEPTED events by running a final security gate check.

    Args:
        envelope: The incoming event from the event bus.
        code_scanner: The code scanner instance.
        policy_enforcer: The policy enforcer instance.
    """
    logger.info(
        "handling proposal_accepted event",
        event_type=envelope.type,
        event_id=envelope.id,
    )
    payload = envelope.payload or {}
    code = payload.get("final_code", payload.get("code", ""))
    file_path = payload.get("file_path", "accepted_proposal")

    if code:
        from security_immune.models import CodeScanInput

        scan_input = CodeScanInput(code=code, file_path=file_path)
        result = await code_scanner.scan_code(scan_input)
        decision = await policy_enforcer.evaluate_gate([result])
        await policy_enforcer.enforce(decision)


async def handle_sandbox_command(
    envelope: EventEnvelope,
    runtime_monitor: RuntimeMonitor,
) -> None:
    """Handle SANDBOX_COMMAND events by analysing runtime activity.

    Args:
        envelope: The incoming event from the event bus.
        runtime_monitor: The runtime monitor instance.
    """
    logger.debug(
        "handling sandbox_command event",
        event_type=envelope.type,
        event_id=envelope.id,
    )
    payload = envelope.payload or {}

    from security_immune.models import RuntimeAnomalyReport

    report = RuntimeAnomalyReport(
        sandbox_id=payload.get("sandbox_id", "unknown"),
        network_connections=payload.get("network_connections", []),
        file_accesses=payload.get("file_accesses", []),
        processes_spawned=payload.get("processes_spawned", []),
    )
    await runtime_monitor.analyze_sandbox_activity(report)


async def handle_agent_spawned(
    envelope: EventEnvelope,
) -> None:
    """Handle AGENT_SPAWNED events for audit logging.

    Args:
        envelope: The incoming event from the event bus.
    """
    logger.info(
        "agent spawned — recording for security audit",
        event_type=envelope.type,
        event_id=envelope.id,
        correlation_id=envelope.correlation_id,
    )
