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
    # Knowledge & Memory
    KNOWLEDGE_ACQUIRED = "knowledge.acquired"
    KNOWLEDGE_PATTERN_EXTRACTED = "knowledge.pattern_extracted"
    KNOWLEDGE_HEURISTIC_CREATED = "knowledge.heuristic_created"
    KNOWLEDGE_COMPRESSION_COMPLETED = "knowledge.compression_completed"
    # Economic Governor
    BUDGET_THRESHOLD_ALERT = "budget.threshold_alert"
    BUDGET_TIER_DOWNGRADE = "budget.tier_downgrade"
    BUDGET_TASK_PAUSED = "budget.task_paused"
    BUDGET_HALT = "budget.halt"
    BUDGET_SPIN_DETECTED = "budget.spin_detected"
    EFFICIENCY_UPDATED = "efficiency.updated"
    # Human Interface
    ESCALATION_CREATED = "escalation.created"
    ESCALATION_RESOLVED = "escalation.resolved"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"


class EvalLayer(StrEnum):
    COMPILATION = "compilation"
    UNIT_TESTS = "unit_tests"
    INTEGRATION_TESTS = "integration_tests"
    ADVERSARIAL = "adversarial"
    SPEC_COMPLIANCE = "spec_compliance"
    ARCHITECTURE = "architecture"
    REGRESSION = "regression"


# ── Phase 3: Economic Governor ────────────────────────────────────
class EnforcementLevel(StrEnum):
    NONE = "none"
    ALERT = "alert"
    RESTRICT = "restrict"
    HALT = "halt"


class BudgetPhase(StrEnum):
    SPECIFICATION = "specification"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    DEBUGGING = "debugging"
    CONTINGENCY = "contingency"


# ── Phase 3: Knowledge & Memory ───────────────────────────────────
class MemoryLayer(StrEnum):
    L0_WORKING = "l0_working"
    L1_PROJECT = "l1_project"
    L2_PATTERN = "l2_pattern"
    L3_HEURISTIC = "l3_heuristic"
    L4_META = "l4_meta"


class ContentType(StrEnum):
    DOCUMENTATION = "documentation"
    EXAMPLE = "example"
    PATTERN = "pattern"
    HEURISTIC = "heuristic"
    STRATEGY = "strategy"


class ObservationType(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PERFORMANCE = "performance"
    WORKAROUND = "workaround"


# ── Phase 3: Human Interface ─────────────────────────────────────
class EscalationCategory(StrEnum):
    CONFIDENCE = "confidence"
    SECURITY = "security"
    BUDGET = "budget"
    ARCHITECTURAL = "architectural"


class EscalationSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    AUTO_RESOLVED = "auto_resolved"


class ApprovalGateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
