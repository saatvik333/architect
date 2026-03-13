# ARCHITECT -- System Architecture

This document describes the design principles, component architecture, data flow, and technology decisions behind ARCHITECT.

---

## Design Principles

### 1. The loop is the product

ARCHITECT does not generate code; it runs the full engineering loop: specify, build, test, deploy, observe, repair, learn. Every component exists to close one part of that loop. A component that does not feed back into the loop has no place in the system.

### 2. Evaluation is harder than generation

LLMs can produce plausible code quickly. The hard problem is knowing whether that code is correct. ARCHITECT invests more architectural complexity in its 7-layer evaluation pipeline than in its code generation agent. Generation without evaluation is just autocomplete.

### 3. Agents are disposable, state is sacred

Any coding agent can be killed, restarted, or replaced mid-task. The World State Ledger and event log survive everything. All agent output goes through a proposal pipeline before it touches persistent state. No agent is trusted; every mutation is validated.

### 4. Economic pressure produces intelligence

Token budgets are not guardrails -- they are forcing functions. When an agent has limited retries and limited tokens, it must plan better, generate tighter code, and learn from failures. The Economic Governor (Phase 3) will make this pressure explicit and dynamic.

### 5. Humans stay in the loop until they choose to leave

ARCHITECT is designed for increasing autonomy, not full autonomy from day one. Every phase adds capability. The Human Interface (Phase 5) provides dashboards, escalation paths, and approval gates. Humans opt out gradually as trust builds.

---

## System Architecture

```
                              USER
                               |
                     +---------+---------+
                     |  CLI / API GW     |
                     |  (apps/)          |
                     +---------+---------+
                               |
               +---------------+----------------+
               |                                |
               v                                v
     +---------+----------+           +---------+---------+
     |  Spec Engine [P2]  |           |  Human Interface  |
     |  parse/validate    |           |  [P5] dashboard   |
     +--------+-----------+           +-------------------+
              |
              v
     +--------+-----------+
     |  Task Graph Engine  |<-----------------------------------+
     |  (DAG + scheduler)  |                                    |
     +--+-----+--------+--+                                    |
        |     |        |                                       |
        |     |        +------------------+                    |
        v     v                           v                    |
  +-----+--+ +--------+        +---------+---------+          |
  | Multi- | | Agent   |        |  Coding Agent     |          |
  | Model  | | Comm    |        |  plan -> gen ->   |          |
  | Router | | Bus     |        |  test -> fix      |          |
  | [P2]   | | [P2]    |        +--------+----------+          |
  +--------+ +--------+                  |                     |
                                         v                     |
                               +---------+---------+           |
                               |  Execution Sandbox |           |
                               |  (Docker isolation)|           |
                               +---------+---------+           |
                                         |                     |
                                         v                     |
                               +---------+---------+           |
                               | Evaluation Engine  |           |
                               | L1: Compilation    |           |
                               | L2: Unit Tests     |           |
                               | L3: Integration    |           |
                               | L4: Adversarial    |           |
                               | L5: Spec Compliance|           |
                               | L6: Architecture   |           |
                               | L7: Regression     |           |
                               +---------+---------+           |
                                         |                     |
                          +--------------+--------------+      |
                          |              |              |      |
                       PASS          FAIL_SOFT      FAIL_HARD  |
                          |              |              |      |
                          v              v              v      |
               +----------+--+  +--------+---+  +------+---+  |
               | World State |  | Retry with |  | Escalate |  |
               | Ledger      |  | error ctx  +->| or mark  |  |
               | (commit)    |  +------------+  | failed   |  |
               +------+------+                  +-----+----+  |
                      |                               |        |
     +----------------+----------------+              |        |
     |                |                |              +--------+
     v                v                v
+----+------+  +------+------+  +-----+-------+
| Knowledge |  | Economic    |  | Security    |
| Memory    |  | Governor    |  | Immune      |
| [P3]      |  | [P3]        |  | [P3]        |
+-----------+  +-------------+  +-------------+

     +-------------------+    +-------------------+
     | Deployment        |    | Failure Taxonomy  |
     | Pipeline [P4]     |    | [P4]              |
     +-------------------+    +-------------------+
```

---

## Component Deep Dive

### 1. World State Ledger (Phase 1) -- IMPLEMENTED

**Purpose:** Single source of truth for the entire system. Every piece of mutable state -- task status, budget consumption, agent activity, build results, repo state -- lives in the versioned world state.

**Key abstractions:**
- `WorldState` -- Mutable top-level state snapshot containing `SpecState`, `RepoState`, `BuildState`, `InfraState`, `AgentState`, `BudgetState`
- `Proposal` -- An immutable mutation request containing a list of `StateMutation` objects
- `StateMutation` -- A single field-level change addressed by dot-path (e.g. `"budget.consumed_tokens"`) with `old_value` / `new_value` for optimistic concurrency
- `StateManager` -- Core class that handles reads (cache-first, DB fallback), proposal submission, validation, and atomic commits
- `EventLog` -- Append-only PostgreSQL event log with idempotent writes
- `StateCache` -- Redis-backed cache for hot state reads

**Communication:** Publishes events via Redis Streams (`proposal.created`, `proposal.accepted`, `proposal.rejected`, `ledger.updated`). All other components read state through the Ledger's API or Temporal activities.

**Implementation:** `services/world-state-ledger/` -- `state_manager.py` (340 lines), `event_log.py`, `cache.py`, `models.py`, FastAPI routes, Temporal activities and worker.

---

### 2. Task Graph Engine (Phase 1) -- IMPLEMENTED

**Purpose:** Decomposes high-level specifications into a DAG of executable tasks, manages dependencies, and schedules work based on priority and readiness.

**Key abstractions:**
- `TaskDAG` -- NetworkX-backed directed acyclic graph where each node stores a `Task` and edges represent dependency relationships
- `TaskDecomposer` -- Converts a spec dict into a list of `Task` objects. Phase 1 uses deterministic decomposition (impl -> test -> review per module). Phase 2+ uses LLM-assisted decomposition
- `TaskScheduler` -- Picks the highest-priority ready task, manages lifecycle transitions (`PENDING -> RUNNING -> COMPLETED/FAILED`), enforces valid state transitions, handles retry logic
- `Task` -- Frozen Pydantic model with `TaskId`, `TaskType`, `AgentType`, `ModelTier`, priority, dependencies, budget, retry history

**Communication:** Publishes task lifecycle events (`task.created`, `task.started`, `task.completed`, `task.failed`, `task.retried`). Reads from the World State Ledger. Persists to Postgres via `TaskRepository`.

**Implementation:** `services/task-graph-engine/` -- `graph.py` (DAG operations), `decomposer.py` (spec-to-tasks), `scheduler.py` (lifecycle management), Temporal workflows for orchestration.

---

### 3. Execution Sandbox (Phase 1) -- IMPLEMENTED

**Purpose:** Provides isolated, resource-limited Docker containers for running generated code. No code touches the host filesystem.

**Key abstractions:**
- `DockerExecutor` -- Creates containers, runs commands, writes/reads files via tar archives, destroys containers. Each sandbox session maps to one container
- `SandboxSession` -- Tracks container ID, status, audit log, resource usage, and timestamps
- `SandboxSpec` -- Defines the sandbox configuration: base image, resource limits, task/agent IDs
- `SecurityValidator` -- Rejects dangerous commands (e.g. network access, privilege escalation) and suspicious file paths before execution
- `ResourceLimits` -- CPU, memory, disk, and timeout constraints applied to containers

**Communication:** Exposes a FastAPI HTTP API. Called by the Coding Agent (via `SandboxClient`) and the Evaluation Engine. Publishes sandbox lifecycle events.

**Implementation:** `services/execution-sandbox/` -- `docker_executor.py` (328 lines), `security.py`, `resource_limits.py`, `file_manager.py`, `models.py`.

---

### 4. Evaluation Engine (Phase 1) -- IMPLEMENTED

**Purpose:** Multi-layer evaluation pipeline that determines whether generated code meets quality standards. Evaluation is fail-fast by default -- a FAIL_HARD in an early layer skips remaining layers.

**Key abstractions:**
- `Evaluator` -- Orchestrates the layer pipeline. Runs each layer in sequence, publishes per-layer events, computes overall verdict
- `EvalLayerBase` -- Abstract base class defining the `evaluate(sandbox_session_id) -> LayerEvaluation` contract
- `CompilationLayer` -- Runs `python -m py_compile` on all Python files. FAIL_HARD on syntax errors
- `UnitTestLayer` -- Runs `pytest` in the sandbox. FAIL_SOFT on test failures (retryable), FAIL_HARD on complete breakage
- `EvaluationReport` -- Aggregates all layer results with an overall `EvalVerdict` (PASS / FAIL_SOFT / FAIL_HARD)
- `LayerEvaluation` -- Per-layer result containing the layer name, verdict, detailed results, and timestamps

**Communication:** Publishes `eval.layer_completed` and `eval.completed` events. Reads from sandboxes via `SandboxClient`. Results are consumed by the Task Graph Engine to determine task completion or retry.

**Implementation:** `services/evaluation-engine/` -- `evaluator.py`, `layers/base.py`, `layers/compilation.py`, `layers/unit_tests.py`, `models.py`.

---

### 5. Coding Agent (Phase 1) -- IMPLEMENTED

**Purpose:** LLM-powered agent that plans an implementation approach, generates code, writes it to a sandbox, runs tests, and iterates on failures.

**Key abstractions:**
- `CodingAgentLoop` -- Orchestrates the full agent lifecycle: plan -> generate -> write to sandbox -> test -> fix -> iterate
- `TaskPlanner` -- Uses the LLM to produce an implementation plan from spec and codebase context
- `CodeGenerator` -- Uses the LLM to produce source files and test files. Also has `fix_errors()` for iterating on failures
- `AgentRun` -- Input model containing task ID, spec context, codebase context, and configuration
- `AgentOutput` -- Result model with generated files, commit message, reasoning summary, and token usage
- `AgentConfig` -- Controls model ID, temperature, max tokens, and generation parameters

**Communication:** Calls the Execution Sandbox via `SandboxClient`. Uses `LLMClient` for Claude API calls. Publishes `agent.completed` events. Orchestrated by Temporal workflows.

**Implementation:** `services/coding-agent/` -- `agent.py` (220 lines), `coder.py`, `planner.py`, `context_builder.py`, `models.py`, Temporal workflows and activities.

---

### 6. Spec Engine (Phase 2) -- STUB

**Purpose:** Will parse, validate, version, and diff project specifications. Converts natural language or structured input into a canonical spec format consumable by the Task Graph Engine.

---

### 7. Multi-Model Router (Phase 2) -- STUB

**Purpose:** Will route LLM requests to the optimal model tier based on task complexity, budget constraints, and historical performance. See the Multi-Model Routing section below.

---

### 8. Codebase Comprehension (Phase 2) -- STUB

**Purpose:** Will build AST-level and embedding-based understanding of the target codebase. Provides context to the Coding Agent about existing code structure, patterns, and conventions.

---

### 9. Agent Comm Bus (Phase 2) -- STUB

**Purpose:** Will provide NATS-backed inter-agent messaging for coordination, work-stealing, and collaborative problem-solving between multiple concurrent agents.

---

### 10. Knowledge Memory (Phase 3) -- STUB

**Purpose:** Will implement a 5-layer memory hierarchy: working memory (current task), episodic memory (past runs), semantic memory (patterns), procedural memory (learned techniques), and meta-cognitive memory (self-assessment).

---

### 11. Economic Governor (Phase 3) -- STUB

**Purpose:** Will enforce token budgets dynamically, adjust model tier allocation based on burn rate, pause low-priority work when budget runs low, and produce cost reports.

---

### 12. Security Immune (Phase 3) -- STUB

**Purpose:** Will scan generated code for security vulnerabilities, dependency risks, and policy violations before any code is committed or deployed.

---

### 13. Deployment Pipeline (Phase 4) -- STUB

**Purpose:** Will manage canary deployments, health monitoring, traffic shifting, and automatic rollback when deployed code degrades production metrics.

---

### 14. Failure Taxonomy (Phase 4) -- STUB

**Purpose:** Will classify failures into structured categories, track root causes, and feed failure patterns back into the Knowledge Memory so agents avoid repeating mistakes.

---

### 15. Human Interface (Phase 5) -- STUB

**Purpose:** Will provide a web dashboard for monitoring system state, reviewing agent output, approving deployments, and configuring escalation policies.

---

## Data Flow

The complete lifecycle of a task from submission to completion:

1. **User submits a spec** via the CLI (`architect submit`) or API Gateway. The spec contains a project description and module breakdown.

2. **Task Graph Engine decomposes the spec** into a DAG of tasks. In Phase 1, each module produces a triplet: implementation task -> test task -> review task. Dependencies are encoded as graph edges.

3. **Scheduler picks the next ready task.** A task is "ready" when all its predecessors in the DAG are completed. Among ready tasks, the highest-priority one is selected. The task transitions from `PENDING` to `RUNNING`.

4. **Coding Agent receives the task** via a Temporal workflow. It:
   - Builds a context window from the spec and codebase
   - Plans the implementation approach via Claude
   - Generates source code and test files via Claude
   - Writes files to an Execution Sandbox

5. **Evaluation Engine runs the pipeline** against the sandbox:
   - **L1 Compilation:** `py_compile` on all Python files
   - **L2 Unit Tests:** `pytest` execution with failure parsing
   - (L3--L7 in later phases)

6. **If PASS:** The task is marked completed. The scheduler unblocks dependent tasks and picks the next one. A proposal is submitted to the World State Ledger recording the state change.

7. **If FAIL_SOFT:** The task has retries remaining. Error context is fed back to the Coding Agent, which calls `fix_errors()` to produce a corrected version. The loop repeats from step 4.

8. **If FAIL_HARD:** The task is marked failed. If retries are exhausted, the task is escalated (logged, and in Phase 5, surfaced to the human dashboard). Dependent tasks are blocked.

9. **World State Ledger records all transitions.** Every status change, proposal, and evaluation result is persisted as an event in the append-only event log and as a versioned state snapshot.

---

## State Management

### Proposal-gated mutations

No component directly mutates the world state. Instead:

```
Agent produces output
       |
       v
Proposal created (list of StateMutations with dot-paths)
       |
       v
Validator checks:
  - old_value matches current state (optimistic concurrency)
  - budget constraints not violated
  - mutation paths are valid
       |
       +-- VALID --> Atomic commit: new ledger version, cache update, events published
       |
       +-- INVALID --> Rejection with reason, event published
```

Each `StateMutation` contains:
- `path`: Dot-separated field address (e.g. `"budget.consumed_tokens"`)
- `old_value`: Expected current value (for optimistic concurrency check)
- `new_value`: The value to write

### Event sourcing

All state changes are logged as events in an append-only PostgreSQL table with idempotent writes (via `idempotency_key` with ON CONFLICT DO NOTHING). Events carry type, timestamp, correlation ID, and payload.

Events are also published to Redis Streams for real-time consumption by other components. Stream names follow the pattern `architect:{event_type}` (e.g. `architect:task.completed`).

### Caching

Redis serves as the hot cache for the current world state snapshot. The `StateCache` class provides `get_current_state()` and `set_current_state()`. On cache miss, the StateManager falls back to the latest PostgreSQL ledger row.

---

## Multi-Model Routing (Phase 2+)

The system defines three model tiers in `architect_common.enums.ModelTier`:

| Tier | Class | Use Cases |
|------|-------|-----------|
| **Tier 1** (Opus) | Maximum capability | Architecture decisions, security review, novel problem-solving, complex refactors |
| **Tier 2** (Sonnet) | Balanced | Feature implementation, test writing, code review, task decomposition |
| **Tier 3** (Haiku) | Fast and cheap | Scaffolding, boilerplate generation, formatting, simple fixes |

In Phase 1, each `Task` carries a `model_tier` field set during decomposition. The Coding Agent uses this to select the model. In Phase 2, the Multi-Model Router will dynamically reassign tiers based on:
- Task complexity (estimated from spec and dependency depth)
- Budget remaining vs. budget consumed
- Historical success rates per tier for similar task types
- Time pressure (deadline proximity)

---

## Evaluation Layers

| Layer | Name | Phase | Verdict on Failure | Auto-fix Behavior |
|-------|------|-------|--------------------|-------------------|
| L1 | Compilation | P1 | FAIL_HARD | Not retryable -- syntax errors must be fixed by regeneration |
| L2 | Unit Tests | P1 | FAIL_SOFT | Errors fed back to agent for iterative fixing |
| L3 | Integration Tests | P2 | FAIL_SOFT | Errors fed back with broader context |
| L4 | Adversarial | P3 | FAIL_SOFT | Edge cases and malicious inputs tested, agent re-generates |
| L5 | Spec Compliance | P2 | FAIL_HARD | Output must match spec; fundamental misunderstanding is not retryable |
| L6 | Architecture Review | P3 | FAIL_SOFT | LLM-as-judge reviews design patterns and conventions |
| L7 | Regression | P4 | FAIL_HARD | Existing tests must not break; regressions block deployment |

The evaluator runs layers in order. When `fail_fast=True` (the default), a FAIL_HARD verdict in any layer short-circuits the remaining layers.

---

## Technology Decisions

### Why uv workspaces

The monorepo contains 24 Python packages (6 libs, 15 services, 2 apps, 1 root). uv workspaces provide:
- Single lockfile (`uv.lock`) for reproducible installs across all packages
- Fast dependency resolution and installation (10--100x faster than pip)
- Workspace-aware `--all-packages` flag for installing everything in one command
- Editable installs by default within the workspace

### Why Temporal

The task execution loop involves multi-step workflows that may fail partway through (LLM call -> sandbox execution -> evaluation). Temporal provides:
- **Durable execution:** Workflows survive process restarts. If a worker crashes mid-task, Temporal replays the workflow from the last checkpoint
- **Built-in retries:** Activity-level retry policies with exponential backoff
- **Visibility:** The Temporal UI (port 8080) shows running workflows, their state, and history
- **Timeouts:** Per-activity and per-workflow timeouts prevent runaway tasks

### Why proposal-gated state

Direct state mutation by agents would create race conditions and make debugging impossible. The proposal pipeline provides:
- **Audit trail:** Every state change has a proposal ID, agent ID, rationale, and timestamp
- **Optimistic concurrency:** The `old_value` check in each mutation prevents lost updates when multiple agents try to modify the same field
- **Rollback-friendly:** Since every ledger version is a full snapshot, point-in-time state recovery is trivial
- **Budget enforcement:** The validator rejects any proposal that would drive `remaining_tokens` below zero

### Why Docker sandboxing

Generated code is untrusted by definition. Docker containers provide:
- **Filesystem isolation:** Code runs in `/workspace` inside the container; the host filesystem is never exposed
- **Resource limits:** CPU, memory, and timeout constraints prevent runaway processes
- **Security scanning:** Commands are validated against a blocklist before execution (no network access, no privilege escalation, no host mounts)
- **Reproducibility:** Each sandbox starts from a known base image with deterministic state
- **User isolation:** Commands run as UID 1000 (non-root) inside the container

### Why Pydantic frozen models

All domain models (`Task`, `Proposal`, `StateMutation`, `EvaluationReport`, etc.) inherit from `ArchitectBase`, which sets `frozen=True`:
- **Immutability:** Once created, a domain model cannot be accidentally mutated. State changes produce new instances via `model_copy(update={...})`
- **Thread safety:** Frozen models can be safely shared across async tasks and Temporal activities
- **Hashability:** Frozen models can be used as dict keys or set members
- **Correctness:** Eliminates a large class of bugs where shared mutable state is modified in unexpected order

The one exception is `WorldState`, which inherits from `MutableBase` because it serves as an accumulator that is built up through successive mutations before being committed as a frozen ledger snapshot.
