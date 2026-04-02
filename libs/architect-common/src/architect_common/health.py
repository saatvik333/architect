"""Shared health check response model."""

from __future__ import annotations

from pydantic import BaseModel

from architect_common.enums import HealthStatus


class HealthResponse(BaseModel):
    """Standard health check response for all services."""

    service: str
    status: HealthStatus
    uptime_seconds: float = 0.0
