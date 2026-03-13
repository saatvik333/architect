"""Abstract base class for all evaluation layers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from architect_common.enums import EvalLayer
from evaluation_engine.models import LayerEvaluation


class EvalLayerBase(ABC):
    """Interface every evaluation layer must implement.

    Each layer runs a specific check (compilation, unit tests, linting, etc.)
    inside a sandbox session and returns a :class:`LayerEvaluation`.
    """

    @property
    @abstractmethod
    def layer_name(self) -> EvalLayer:
        """The :class:`EvalLayer` enum value identifying this layer."""

    @abstractmethod
    async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
        """Run this evaluation layer inside the given sandbox session.

        Args:
            sandbox_session_id: The active sandbox session to run checks in.

        Returns:
            A :class:`LayerEvaluation` with the layer verdict and details.
        """
