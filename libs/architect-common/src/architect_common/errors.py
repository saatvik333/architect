"""Exception hierarchy for the ARCHITECT system."""

from __future__ import annotations


class ArchitectError(Exception):
    """Base exception for all ARCHITECT errors."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


# ── World State ───────────────────────────────────────────────────
class LedgerError(ArchitectError):
    """Errors related to the World State Ledger."""


class ProposalRejectedError(LedgerError):
    """A state mutation proposal was rejected by the validator."""


class OptimisticConcurrencyError(LedgerError):
    """State changed between read and write (stale version)."""


class LedgerVersionNotFoundError(LedgerError):
    """Requested ledger version does not exist."""


# ── Task Graph ────────────────────────────────────────────────────
class TaskGraphError(ArchitectError):
    """Errors related to the Task Graph Engine."""


class TaskNotFoundError(TaskGraphError):
    """Referenced task does not exist."""


class CircularDependencyError(TaskGraphError):
    """Task graph contains a cycle."""


class InvalidTransitionError(TaskGraphError):
    """Invalid task status transition."""


# ── Sandbox ───────────────────────────────────────────────────────
class SandboxError(ArchitectError):
    """Errors related to the Execution Sandbox."""


class SandboxTimeoutError(SandboxError):
    """Sandbox execution exceeded time limit."""


class SandboxResourceError(SandboxError):
    """Sandbox exceeded resource limits (memory, disk, etc.)."""


class SandboxSecurityError(SandboxError):
    """Security violation detected in sandbox."""


# ── Evaluation ────────────────────────────────────────────────────
class EvaluationError(ArchitectError):
    """Errors related to the Evaluation Engine."""


class CompilationError(EvaluationError):
    """Code failed to compile/parse."""


class TestExecutionError(EvaluationError):
    """Test execution failed (not test failures — execution itself)."""


# ── Agent ─────────────────────────────────────────────────────────
class AgentError(ArchitectError):
    """Errors related to coding agents."""


class AgentBudgetExhaustedError(AgentError):
    """Agent exceeded its token/time budget."""


class AgentContextOverflowError(AgentError):
    """Context too large for the target model."""


# ── LLM ───────────────────────────────────────────────────────────
class LLMError(ArchitectError):
    """Errors related to LLM API calls."""


class LLMRateLimitError(LLMError):
    """Rate limit hit on LLM API."""


class LLMResponseError(LLMError):
    """Unexpected or malformed LLM response."""


# ── Budget ────────────────────────────────────────────────────────
class BudgetError(ArchitectError):
    """Errors related to economic governance."""


class BudgetExhaustedError(BudgetError):
    """Total project budget has been exhausted."""


class BudgetWarningError(BudgetError):
    """Budget warning threshold reached."""
