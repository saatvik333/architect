"""FastAPI route definitions for the Agent Communication Bus."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agent_comm_bus.api.dependencies import get_message_bus
from agent_comm_bus.bus import MessageBus
from agent_comm_bus.models import AgentMessage, MessageStats
from architect_common.enums import HealthStatus

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    service: str = "agent-comm-bus"
    status: HealthStatus


class PublishRequest(BaseModel):
    """Request body for POST /api/v1/bus/publish."""

    subject: str = Field(description="NATS subject to publish to.")
    message: dict[str, Any] = Field(description="Serialised AgentMessage.")


class PublishResponse(BaseModel):
    """Response body for POST /api/v1/bus/publish."""

    message_id: str
    subject: str
    status: str = "published"


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)


@router.get("/api/v1/bus/health", response_model=HealthResponse)
async def bus_health() -> HealthResponse:
    """Bus-specific health check endpoint."""
    return HealthResponse(status=HealthStatus.HEALTHY)


@router.get("/api/v1/bus/stats", response_model=MessageStats)
async def bus_stats(
    bus: MessageBus = Depends(get_message_bus),
) -> MessageStats:
    """Return current message bus statistics."""
    return bus.stats


@router.post("/api/v1/bus/publish", response_model=PublishResponse)
async def publish_message(
    body: PublishRequest,
    bus: MessageBus = Depends(get_message_bus),
) -> PublishResponse:
    """Publish an agent message to the bus."""
    message = AgentMessage.model_validate(body.message)
    await bus.publish(body.subject, message)
    return PublishResponse(message_id=message.id, subject=body.subject)
