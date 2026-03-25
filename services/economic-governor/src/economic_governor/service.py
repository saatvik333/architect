"""FastAPI application factory for the Economic Governor service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from architect_common.enums import EventType
from architect_common.logging import get_logger, setup_logging
from architect_events.publisher import EventPublisher
from architect_events.subscriber import EventSubscriber
from architect_observability import init_observability, shutdown_observability
from economic_governor.api.dependencies import (
    cleanup,
    get_config,
    set_budget_tracker,
    set_efficiency_scorer,
    set_enforcer,
)
from economic_governor.api.routes import router
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer
from economic_governor.monitor import Monitor
from economic_governor.spin_detector import SpinDetector

logger = get_logger(component="economic_governor.service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle for the Economic Governor."""
    config: EconomicGovernorConfig = app.state.config

    # ── Event publisher ──────────────────────────────────────────────
    event_publisher = EventPublisher(config.architect.redis.url)
    await event_publisher.connect()

    # ── Core components ──────────────────────────────────────────────
    budget_tracker = BudgetTracker(config)
    spin_detector = SpinDetector(config)
    efficiency_scorer = EfficiencyScorer()
    enforcer = Enforcer(config, event_publisher)
    await enforcer.startup()

    # Wire into DI.
    set_budget_tracker(budget_tracker)
    set_efficiency_scorer(efficiency_scorer)
    set_enforcer(enforcer)

    # ── Monitor ──────────────────────────────────────────────────────
    monitor = Monitor(
        config=config,
        budget_tracker=budget_tracker,
        spin_detector=spin_detector,
        efficiency_scorer=efficiency_scorer,
        enforcer=enforcer,
    )

    # ── Event subscriptions ──────────────────────────────────────────
    subscriber = EventSubscriber(
        redis_url=config.architect.redis.url,
        group="economic-governor",
        consumer="econ-gov-1",
    )
    subscriber.on(EventType.AGENT_COMPLETED, monitor.handle_agent_completed)
    subscriber.on(EventType.TASK_COMPLETED, monitor.handle_task_completed)
    subscriber.on(EventType.TASK_FAILED, monitor.handle_task_failed)
    subscriber.on(EventType.ROUTING_DECISION, monitor.handle_routing_decision)

    event_types = [
        EventType.AGENT_COMPLETED,
        EventType.TASK_COMPLETED,
        EventType.TASK_FAILED,
        EventType.ROUTING_DECISION,
    ]

    try:
        await subscriber.start(event_types)
        logger.info("event subscriber started")
    except Exception:
        logger.warning("event subscriber failed to start — running without it", exc_info=True)

    # ── Background monitoring loop ───────────────────────────────────
    monitor_task = monitor.start()

    logger.info("economic-governor service started", port=config.port)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    shutdown_observability(app)

    monitor.stop()
    with suppress(asyncio.CancelledError):
        await monitor_task

    await subscriber.stop()
    await event_publisher.close()
    await cleanup()

    logger.info("economic-governor service stopped")


def create_app(config: EconomicGovernorConfig | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if config is None:
        config = get_config()

    setup_logging(log_level=config.log_level)

    app = FastAPI(
        title="ARCHITECT Economic Governor",
        description="Cost management, budget enforcement, and resource allocation for the ARCHITECT system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.include_router(router)
    init_observability(app, "economic-governor")

    return app


def main() -> None:
    """CLI entry point: ``python -m economic_governor.service``."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "economic_governor.service:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
