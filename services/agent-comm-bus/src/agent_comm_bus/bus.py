"""NATS JetStream-backed message bus for inter-agent communication."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

import nats
import nats.js
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext

from agent_comm_bus.models import AgentMessage, MessageStats
from architect_common.errors import ArchitectError
from architect_common.logging import get_logger

logger = get_logger(component="message-bus")


class MessageBusError(ArchitectError):
    """Errors related to the Agent Communication Bus."""


class MessageTimeoutError(MessageBusError):
    """Request-reply timed out."""


class MessageBus:
    """NATS JetStream typed inter-agent messaging bus.

    Provides publish/subscribe and request-reply patterns for
    communication between ARCHITECT agents.
    """

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        stream_name: str = "ARCHITECT",
    ) -> None:
        self._nats_url = nats_url
        self._stream_name = stream_name
        self._nc: NATSClient | None = None
        self._js: JetStreamContext | None = None
        self._subscriptions: list[Any] = []
        # Mutable internal tracking — the frozen MessageStats model is built on read.
        self._stats_data: dict[str, Any] = {
            "total_published": 0,
            "total_received": 0,
            "by_type": {},
            "dead_letter_count": 0,
            "active_subscriptions": 0,
        }

    async def connect(self) -> None:
        """Connect to NATS and ensure the JetStream stream exists."""
        self._nc = await nats.connect(self._nats_url)
        self._js = self._nc.jetstream()
        await self._ensure_stream()
        logger.info("connected to NATS", url=self._nats_url, stream=self._stream_name)

    async def close(self) -> None:
        """Drain all subscriptions and close the NATS connection."""
        for sub in self._subscriptions:
            with contextlib.suppress(Exception):
                await sub.unsubscribe()
        self._subscriptions.clear()
        self._stats_data["active_subscriptions"] = 0

        if self._nc is not None and not self._nc.is_closed:
            await self._nc.close()
            self._nc = None
            self._js = None
        logger.info("message bus closed")

    async def publish(self, subject: str, message: AgentMessage) -> None:
        """Serialize *message* to JSON and publish via JetStream."""
        if self._js is None:
            raise MessageBusError("Not connected — call connect() first")

        data = message.model_dump_json().encode()
        await self._js.publish(subject, data)

        self._stats_data["total_published"] += 1
        msg_type = message.message_type.value
        self._stats_data["by_type"][msg_type] = self._stats_data["by_type"].get(msg_type, 0) + 1
        logger.debug("published", subject=subject, message_id=message.id)

    async def subscribe(
        self,
        subject: str,
        handler: Callable[[AgentMessage], Awaitable[None]],
        queue_group: str | None = None,
    ) -> None:
        """Subscribe to *subject* via JetStream push subscriber.

        Messages are deserialized and passed to *handler*. Stats are updated
        for each received message.
        """
        if self._js is None:
            raise MessageBusError("Not connected — call connect() first")

        async def _callback(msg: Any) -> None:
            agent_message = AgentMessage.model_validate_json(msg.data)
            self._stats_data["total_received"] += 1
            await handler(agent_message)
            await msg.ack()

        kwargs: dict[str, Any] = {}
        if queue_group is not None:
            kwargs["queue"] = queue_group

        sub = await self._js.subscribe(subject, cb=_callback, **kwargs)
        self._subscriptions.append(sub)
        self._stats_data["active_subscriptions"] = len(self._subscriptions)
        logger.debug("subscribed", subject=subject, queue_group=queue_group)

    async def request(
        self,
        subject: str,
        message: AgentMessage,
        timeout: float = 5.0,
    ) -> AgentMessage:
        """Send a request and wait for a reply (request-reply pattern).

        Raises :class:`MessageTimeoutError` if no reply arrives within *timeout*.
        """
        if self._nc is None:
            raise MessageBusError("Not connected — call connect() first")

        data = message.model_dump_json().encode()
        try:
            reply = await self._nc.request(subject, data, timeout=timeout)
        except nats.errors.TimeoutError as exc:
            raise MessageTimeoutError(
                f"Request to {subject} timed out after {timeout}s",
            ) from exc

        self._stats_data["total_published"] += 1
        response = AgentMessage.model_validate(json.loads(reply.data))
        self._stats_data["total_received"] += 1
        return response

    async def _ensure_stream(self) -> None:
        """Create or update the JetStream stream for ARCHITECT subjects."""
        if self._js is None:
            return

        try:
            await self._js.find_stream_info_by_subject(f"{self._stream_name}.*")
        except Exception:
            await self._js.add_stream(
                name=self._stream_name,
                subjects=[f"{self._stream_name}.*"],
            )
            logger.info("created JetStream stream", stream=self._stream_name)

    @property
    def stats(self) -> MessageStats:
        """Return current statistics as a frozen model."""
        return MessageStats(
            total_published=self._stats_data["total_published"],
            total_received=self._stats_data["total_received"],
            by_type=dict(self._stats_data["by_type"]),
            dead_letter_count=self._stats_data["dead_letter_count"],
            active_subscriptions=self._stats_data["active_subscriptions"],
        )
