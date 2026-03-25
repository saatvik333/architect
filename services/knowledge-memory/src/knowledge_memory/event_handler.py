"""Event subscription handlers for the Knowledge & Memory system.

Listens to task lifecycle events and creates observations for the
compression pipeline to process.
"""

from __future__ import annotations

from architect_common.enums import ObservationType
from architect_common.logging import get_logger
from architect_common.types import AgentId, TaskId, new_knowledge_id
from architect_events.schemas import EventEnvelope
from knowledge_memory.knowledge_store import KnowledgeStore

logger = get_logger(component="knowledge_memory.event_handler")


class KnowledgeEventHandler:
    """Handles events from the event bus to create observations."""

    def __init__(self, knowledge_store: KnowledgeStore) -> None:
        self._store = knowledge_store

    async def handle_task_completed(self, envelope: EventEnvelope) -> None:
        """Create a success observation from a task completion event."""
        payload = envelope.payload
        task_id = TaskId(str(payload.get("task_id", "")))
        agent_id = AgentId(str(payload.get("agent_id", "")))
        verdict = str(payload.get("verdict", ""))

        obs_id = new_knowledge_id()
        description = f"Task {task_id} completed by {agent_id} with verdict: {verdict}"

        await self._store.store_observation(
            obs_id=obs_id,
            task_id=task_id,
            agent_id=agent_id,
            observation_type=ObservationType.SUCCESS,
            description=description,
            context={"verdict": verdict, "correlation_id": envelope.correlation_id or ""},
            outcome=verdict,
        )
        logger.info(
            "created success observation from task completion",
            obs_id=str(obs_id),
            task_id=str(task_id),
        )

    async def handle_task_failed(self, envelope: EventEnvelope) -> None:
        """Create a failure observation from a task failure event."""
        payload = envelope.payload
        task_id = TaskId(str(payload.get("task_id", "")))
        agent_id = AgentId(str(payload.get("agent_id", "")))
        error_message = str(payload.get("error_message", ""))

        obs_id = new_knowledge_id()
        description = f"Task {task_id} failed by {agent_id}: {error_message}"

        await self._store.store_observation(
            obs_id=obs_id,
            task_id=task_id,
            agent_id=agent_id,
            observation_type=ObservationType.FAILURE,
            description=description,
            context={
                "error_message": error_message,
                "correlation_id": envelope.correlation_id or "",
            },
            outcome="failed",
        )
        logger.info(
            "created failure observation from task failure",
            obs_id=str(obs_id),
            task_id=str(task_id),
        )
