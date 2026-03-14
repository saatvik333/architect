"""Shared enumerations for the ARCHITECT system."""

from enum import StrEnum


class StatusEnum(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ProposalVerdict(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvalVerdict(StrEnum):
    PASS = "pass"
    FAIL_SOFT = "fail_soft"
    FAIL_HARD = "fail_hard"


class TaskType(StrEnum):
    IMPLEMENT_FEATURE = "implement_feature"
    WRITE_TEST = "write_test"
    REVIEW_CODE = "review_code"
    FIX_BUG = "fix_bug"
    REFACTOR = "refactor"


class AgentType(StrEnum):
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    PLANNER = "planner"


class ModelTier(StrEnum):
    TIER_1 = "tier_1"  # Opus-class: max capability
    TIER_2 = "tier_2"  # Sonnet-class: balanced
    TIER_3 = "tier_3"  # Haiku-class: fast, cheap


class EnvironmentName(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class BuildResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class LintStatus(StrEnum):
    CLEAN = "clean"
    WARNINGS = "warnings"
    ERRORS = "errors"


class SandboxStatus(StrEnum):
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    ERROR = "error"
    DESTROYED = "destroyed"


class EventType(StrEnum):
    # World State
    LEDGER_UPDATED = "ledger.updated"
    PROPOSAL_CREATED = "proposal.created"
    PROPOSAL_ACCEPTED = "proposal.accepted"
    PROPOSAL_REJECTED = "proposal.rejected"
    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_RETRIED = "task.retried"
    # Agent lifecycle
    AGENT_SPAWNED = "agent.spawned"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    # Sandbox lifecycle
    SANDBOX_CREATED = "sandbox.created"
    SANDBOX_COMMAND = "sandbox.command"
    SANDBOX_DESTROYED = "sandbox.destroyed"
    # Evaluation
    EVAL_STARTED = "eval.started"
    EVAL_LAYER_COMPLETED = "eval.layer_completed"
    EVAL_COMPLETED = "eval.completed"
    # Budget
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXHAUSTED = "budget.exhausted"
    # Specification Engine
    SPEC_CREATED = "spec.created"
    SPEC_CLARIFICATION_NEEDED = "spec.clarification_needed"
    SPEC_FINALIZED = "spec.finalized"
    # Routing
    ROUTING_DECISION = "routing.decision"
    ROUTING_ESCALATION = "routing.escalation"
    # Communication Bus
    MESSAGE_PUBLISHED = "message.published"
    MESSAGE_DEAD_LETTERED = "message.dead_lettered"


class EvalLayer(StrEnum):
    COMPILATION = "compilation"
    UNIT_TESTS = "unit_tests"
    INTEGRATION_TESTS = "integration_tests"
    ADVERSARIAL = "adversarial"
    SPEC_COMPLIANCE = "spec_compliance"
    ARCHITECTURE = "architecture"
    REGRESSION = "regression"
