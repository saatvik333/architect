"""Serialize / deserialize EventEnvelope for Redis Streams."""

from __future__ import annotations

import json

from architect_events.schemas import EventEnvelope


def serialize_event(event: EventEnvelope) -> dict[str, str]:
    """Convert an ``EventEnvelope`` into a flat ``dict[str, str]`` for ``XADD``.

    Redis Stream entries are mappings of ``bytes -> bytes`` so every value
    must be stringified.  We store the full model JSON under a single
    ``"data"`` key to keep round-tripping lossless.
    """
    return {"data": event.model_dump_json()}


def deserialize_event(data: dict[bytes, bytes]) -> EventEnvelope:
    """Reconstruct an ``EventEnvelope`` from the mapping returned by ``XREAD`` / ``XREADGROUP``.

    Redis returns field names and values as ``bytes``, so we decode
    the ``b"data"`` field and parse the JSON back into the model.
    """
    raw = data[b"data"]
    payload = json.loads(raw)
    return EventEnvelope.model_validate(payload)
