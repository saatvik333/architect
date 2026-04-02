"""Generic dependency injection container for FastAPI services."""

from __future__ import annotations


class ServiceDependency[T]:
    """Type-safe dependency slot for FastAPI DI.

    Replaces the repetitive get_X/set_X/cleanup pattern used across services.

    Usage::

        _budget = ServiceDependency[BudgetTracker]("BudgetTracker")
        get_budget_tracker = _budget.get
        set_budget_tracker = _budget.set
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._instance: T | None = None

    def get(self) -> T:
        """Return the stored instance or raise if not set."""
        if self._instance is None:
            raise RuntimeError(f"{self._name} not initialised. Call set() during startup.")
        return self._instance

    def set(self, instance: T) -> None:
        """Store an instance."""
        self._instance = instance

    async def cleanup(self) -> None:
        """Clear the stored instance, calling ``aclose()`` if available."""
        if self._instance is not None and hasattr(self._instance, "aclose"):
            await self._instance.aclose()  # type: ignore[union-attr]
        self._instance = None
