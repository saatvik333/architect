"""Core in-memory budget tracking engine.

Maintains running totals of token consumption and cost, computes burn
rate from a sliding window, and detects threshold crossings that trigger
enforcement actions.
"""

from __future__ import annotations

import time
from collections import deque

from architect_common.enums import BudgetPhase, EnforcementLevel
from architect_common.logging import get_logger
from economic_governor.config import EconomicGovernorConfig
from economic_governor.models import (
    BudgetAllocationRequest,
    BudgetAllocationResult,
    BudgetSnapshot,
    PhaseAllocation,
    PhaseStatus,
)

logger = get_logger(component="economic_governor.budget_tracker")

# Token-per-dollar estimate (rough average across tiers).
_TOKENS_PER_DOLLAR = 1_000_000

# Sliding window duration for burn-rate calculation (seconds).
_BURN_RATE_WINDOW_SECONDS = 300.0  # 5 minutes


class BudgetTracker:
    """Tracks token and cost consumption against an allocated budget.

    All mutations happen in-process; persistence is handled by the
    :class:`~economic_governor.enforcer.Enforcer` on threshold events.
    """

    def __init__(self, config: EconomicGovernorConfig) -> None:
        self._config = config
        self._allocated_tokens: int = config.architect.budget.total_tokens
        self._consumed_tokens: int = 0
        self._consumed_usd: float = 0.0
        self._enforcement_level: EnforcementLevel = EnforcementLevel.NONE

        # Per-phase tracking
        self._phase_allocated: dict[BudgetPhase, int] = self._compute_phase_allocations()
        self._phase_consumed: dict[BudgetPhase, int] = {p: 0 for p in BudgetPhase}

        # Sliding-window deque of (timestamp, tokens) for burn-rate.
        self._consumption_window: deque[tuple[float, int]] = deque()

    # ── Phase allocation helpers ─────────────────────────────────────

    def _phase_pct_mapping(self) -> dict[BudgetPhase, float]:
        """Map each phase to its configured budget percentage."""
        cfg = self._config
        return {
            BudgetPhase.SPECIFICATION: cfg.spec_budget_pct,
            BudgetPhase.PLANNING: cfg.planning_budget_pct,
            BudgetPhase.IMPLEMENTATION: cfg.implementation_budget_pct,
            BudgetPhase.TESTING: cfg.testing_budget_pct,
            BudgetPhase.REVIEW: cfg.review_budget_pct,
            BudgetPhase.DEBUGGING: cfg.debugging_budget_pct,
            BudgetPhase.CONTINGENCY: cfg.contingency_budget_pct,
        }

    def _compute_phase_allocations(self) -> dict[BudgetPhase, int]:
        """Divide the total budget across phases based on config percentages."""
        total = self._allocated_tokens
        return {phase: int(total * pct / 100) for phase, pct in self._phase_pct_mapping().items()}

    # ── Public interface ─────────────────────────────────────────────

    def record_consumption(
        self,
        agent_id: str,
        tokens: int,
        cost_usd: float,
        phase: BudgetPhase = BudgetPhase.IMPLEMENTATION,
    ) -> EnforcementLevel:
        """Record token consumption and return the current enforcement level.

        Args:
            agent_id: The agent that consumed the tokens.
            tokens: Number of tokens consumed.
            cost_usd: Dollar cost of the consumption.
            phase: The development phase the consumption belongs to.

        Returns:
            The current :class:`EnforcementLevel` after this consumption.
        """
        self._consumed_tokens += tokens
        self._consumed_usd += cost_usd
        self._phase_consumed[phase] = self._phase_consumed.get(phase, 0) + tokens

        # Update sliding window.
        now = time.monotonic()
        self._consumption_window.append((now, tokens))
        self._prune_window(now)

        # Check for threshold crossings.
        new_level = self._compute_enforcement_level()
        if new_level != self._enforcement_level:
            logger.warning(
                "enforcement level changed",
                old=self._enforcement_level,
                new=new_level,
                consumed_pct=self.consumed_pct,
                agent_id=agent_id,
            )
        self._enforcement_level = new_level

        return self._enforcement_level

    def get_snapshot(self) -> BudgetSnapshot:
        """Return a point-in-time snapshot of the budget state."""
        return BudgetSnapshot(
            allocated_tokens=self._allocated_tokens,
            consumed_tokens=self._consumed_tokens,
            consumed_pct=self.consumed_pct,
            consumed_usd=self._consumed_usd,
            burn_rate_tokens_per_min=self.burn_rate,
            enforcement_level=self._enforcement_level,
            phase_breakdown=self._build_phase_breakdown(),
        )

    @property
    def consumed_pct(self) -> float:
        """Percentage of allocated tokens consumed."""
        if self._allocated_tokens == 0:
            return 0.0
        return round(self._consumed_tokens / self._allocated_tokens * 100, 2)

    @property
    def burn_rate(self) -> float:
        """Tokens consumed per minute (from the sliding window)."""
        now = time.monotonic()
        self._prune_window(now)
        if not self._consumption_window:
            return 0.0

        oldest_ts = self._consumption_window[0][0]
        elapsed_minutes = (now - oldest_ts) / 60.0
        if elapsed_minutes < 0.001:
            return 0.0

        total = sum(tokens for _, tokens in self._consumption_window)
        return round(total / elapsed_minutes, 2)

    def threshold_crossed(self) -> EnforcementLevel | None:
        """Return the new enforcement level if it differs from current, else None.

        This is useful for one-shot checks without recording consumption.
        """
        new_level = self._compute_enforcement_level()
        if new_level != self._enforcement_level:
            old = self._enforcement_level
            self._enforcement_level = new_level
            logger.info(
                "threshold crossed",
                old=old,
                new=new_level,
                consumed_pct=self.consumed_pct,
            )
            return new_level
        return None

    def allocate_project_budget(self, request: BudgetAllocationRequest) -> BudgetAllocationResult:
        """Compute a budget allocation for a project based on complexity and priority.

        The resulting budget is based on the total configured tokens scaled by
        complexity and priority. This does NOT mutate the tracker state; the
        caller should use the result to initialise a new tracker if needed.
        """
        base_tokens = self._config.architect.budget.total_tokens
        # Scale by complexity (0.5-1.5x) and priority (0.8-1.2x)
        complexity_factor = 0.5 + request.estimated_complexity
        priority_factor = 0.8 + (request.priority - 1) * 0.1
        total_tokens = int(base_tokens * complexity_factor * priority_factor)
        total_usd = round(total_tokens / _TOKENS_PER_DOLLAR, 4)

        phase_allocations = [
            PhaseAllocation(
                phase=phase,
                allocated_tokens=int(total_tokens * pct / 100),
                allocated_pct=pct,
            )
            for phase, pct in self._phase_pct_mapping().items()
        ]

        return BudgetAllocationResult(
            project_id=request.project_id,
            total_tokens=total_tokens,
            total_usd=total_usd,
            phase_allocations=phase_allocations,
        )

    # ── Internals ────────────────────────────────────────────────────

    def _compute_enforcement_level(self) -> EnforcementLevel:
        """Determine the enforcement level from the current consumed percentage."""
        pct = self.consumed_pct
        if pct >= self._config.halt_threshold_pct:
            return EnforcementLevel.HALT
        if pct >= self._config.restrict_threshold_pct:
            return EnforcementLevel.RESTRICT
        if pct >= self._config.alert_threshold_pct:
            return EnforcementLevel.ALERT
        return EnforcementLevel.NONE

    def _prune_window(self, now: float) -> None:
        """Remove entries older than the burn-rate window."""
        cutoff = now - _BURN_RATE_WINDOW_SECONDS
        while self._consumption_window and self._consumption_window[0][0] < cutoff:
            self._consumption_window.popleft()

    def _build_phase_breakdown(self) -> list[PhaseStatus]:
        """Build per-phase status from tracking data."""
        breakdown: list[PhaseStatus] = []
        for phase in BudgetPhase:
            allocated = self._phase_allocated.get(phase, 0)
            consumed = self._phase_consumed.get(phase, 0)
            consumed_pct = round(consumed / allocated * 100, 2) if allocated > 0 else 0.0
            allocated_pct = (
                round(allocated / self._allocated_tokens * 100, 2)
                if self._allocated_tokens > 0
                else 0.0
            )
            breakdown.append(
                PhaseStatus(
                    phase=phase,
                    allocated_tokens=allocated,
                    allocated_pct=allocated_pct,
                    consumed_tokens=consumed,
                    consumed_pct=consumed_pct,
                )
            )
        return breakdown
