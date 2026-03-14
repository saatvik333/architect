"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog


def setup_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog for the ARCHITECT system.

    Args:
        log_level: Python log level name (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, output JSON lines. If False, pretty console output.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: object) -> structlog.stdlib.BoundLogger:
    """Get a bound logger with optional initial context."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(**initial_context))
