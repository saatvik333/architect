"""FastAPI application factory for the Security Immune System service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import partial

from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_events.publisher import EventPublisher
from architect_events.subscriber import EventSubscriber
from architect_observability import init_observability, shutdown_observability
from security_immune.api.dependencies import (
    cleanup,
    get_config,
    set_code_scanner,
    set_dependency_auditor,
    set_policy_enforcer,
    set_prompt_validator,
    set_runtime_monitor,
)
from security_immune.api.routes import router
from security_immune.config import SecurityImmuneConfig
from security_immune.event_handlers import (
    handle_agent_spawned,
    handle_proposal_accepted,
    handle_proposal_created,
    handle_sandbox_command,
)
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator
from security_immune.scanners.runtime_monitor import RuntimeMonitor
from security_immune.temporal.worker import run_worker

logger = get_logger(component="security_immune.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Security Immune System."""
    import time

    app.state.started_at = time.monotonic()
    config: SecurityImmuneConfig = app.state.config

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()

    # ── Core scanner components ──────────────────────────────────────
    code_scanner = CodeScanner(config)
    dependency_auditor = DependencyAuditor(config)
    prompt_validator = PromptValidator()
    runtime_monitor = RuntimeMonitor()
    policy_enforcer = PolicyEnforcer(config)

    # Wire into DI.
    set_code_scanner(code_scanner)
    set_dependency_auditor(dependency_auditor)
    set_prompt_validator(prompt_validator)
    set_runtime_monitor(runtime_monitor)
    set_policy_enforcer(policy_enforcer)

    # ── Event subscriptions ──────────────────────────────────────────
    subscriber = EventSubscriber(
        redis_url=config.architect.redis.url,
        group="security-immune",
        consumer="sec-immune-1",
    )
    subscriber.on(
        EventType.PROPOSAL_CREATED,
        partial(
            handle_proposal_created, code_scanner=code_scanner, policy_enforcer=policy_enforcer
        ),
    )
    subscriber.on(
        EventType.PROPOSAL_ACCEPTED,
        partial(
            handle_proposal_accepted, code_scanner=code_scanner, policy_enforcer=policy_enforcer
        ),
    )
    subscriber.on(
        EventType.SANDBOX_COMMAND,
        partial(handle_sandbox_command, runtime_monitor=runtime_monitor),
    )
    subscriber.on(EventType.AGENT_SPAWNED, handle_agent_spawned)

    event_types = [
        EventType.PROPOSAL_CREATED,
        EventType.PROPOSAL_ACCEPTED,
        EventType.SANDBOX_COMMAND,
        EventType.AGENT_SPAWNED,
    ]

    try:
        await subscriber.start(event_types)
        logger.info("event subscriber started")
    except Exception:
        logger.warning("event subscriber failed to start — running without it", exc_info=True)

    # ── Temporal worker ──────────────────────────────────────────────
    worker_task: asyncio.Task[None] | None = None
    try:
        worker_task = asyncio.create_task(
            run_worker(
                config=config,
                code_scanner=code_scanner,
                dependency_auditor=dependency_auditor,
                prompt_validator=prompt_validator,
                runtime_monitor=runtime_monitor,
                policy_enforcer=policy_enforcer,
            )
        )
        logger.info("temporal worker started as background task")
    except Exception:
        logger.warning("temporal worker failed to start — running without it", exc_info=True)

    logger.info("security-immune service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    shutdown_observability(app)

    if worker_task is not None:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task

    await subscriber.stop()
    await event_publisher.close()
    await cleanup()

    logger.info("security-immune service stopped")


def create_app(config: SecurityImmuneConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = get_config()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="ARCHITECT Security Immune System",
        description="Threat detection, vulnerability scanning, and policy enforcement for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)
    init_observability(app, "security-immune")

    return app


def main() -> None:
    """CLI entry point: ``python -m security_immune.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "security_immune.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
