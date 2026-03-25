"""Spin detection: identifies agents that retry repeatedly without making progress.

An agent is considered "spinning" when it has retried a task beyond
:pyattr:`max_retries` times without producing a meaningful diff (code change).
"""

from __future__ import annotations

from architect_common.logging import get_logger
from architect_common.types import AgentId, TaskId
from economic_governor.config import EconomicGovernorConfig
from economic_governor.models import SpinDetection

logger = get_logger(component="economic_governor.spin_detector")


class SpinDetector:
    """Tracks per-agent/task retry counts and flags spinning behaviour."""

    def __init__(self, config: EconomicGovernorConfig) -> None:
        self._max_retries = config.spin_max_retries
        # Key: (agent_id, task_id) -> (retry_count, tokens_since_last_diff)
        self._state: dict[tuple[str, str], tuple[int, int]] = {}

    def record_retry(
        self,
        agent_id: AgentId,
        task_id: TaskId,
        has_diff: bool,
        tokens: int,
    ) -> SpinDetection:
        """Record a retry attempt and return the spin detection result.

        Args:
            agent_id: The agent performing the retry.
            task_id: The task being retried.
            has_diff: Whether the agent produced a meaningful code change.
            tokens: Tokens consumed in this retry attempt.

        Returns:
            A :class:`SpinDetection` indicating whether the agent is spinning.
        """
        key = (str(agent_id), str(task_id))

        if has_diff:
            # Agent made progress — reset the counter.
            self._state[key] = (0, 0)
            return SpinDetection(
                agent_id=agent_id,
                task_id=task_id,
                is_spinning=False,
                retry_count=0,
                tokens_since_last_diff=0,
            )

        prev_count, prev_tokens = self._state.get(key, (0, 0))
        new_count = prev_count + 1
        new_tokens = prev_tokens + tokens
        self._state[key] = (new_count, new_tokens)

        is_spinning = new_count >= self._max_retries
        if is_spinning:
            logger.warning(
                "spin detected",
                agent_id=str(agent_id),
                task_id=str(task_id),
                retry_count=new_count,
                tokens_wasted=new_tokens,
            )

        return SpinDetection(
            agent_id=agent_id,
            task_id=task_id,
            is_spinning=is_spinning,
            retry_count=new_count,
            tokens_since_last_diff=new_tokens,
        )

    def reset(self, agent_id: AgentId) -> None:
        """Clear all spin-tracking state for an agent (e.g. on task reassignment)."""
        keys_to_remove = [k for k in self._state if k[0] == str(agent_id)]
        for k in keys_to_remove:
            del self._state[k]
        logger.debug("spin state reset", agent_id=str(agent_id))
