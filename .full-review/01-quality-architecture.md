# Phase 1: Code Quality & Architecture Review

## Code Quality Findings

### Critical (3)

1. **C-1. Duplicated Mutation Logic in StateManager Creates Divergence Risk**
   - File: `services/world-state-ledger/src/world_state_ledger/state_manager.py`, lines 244-317
   - `_apply_mutations` and `_validate_mutations` both independently implement dot-path mutation traversal with nearly identical nested-dict walking code. If either copy is modified without updating the other, validation and application diverge, corrupting world state.
   - Fix: Extract shared traversal into a single static `_apply_mutations_to_dict` helper.

2. **C-2. Security Command Filter Can Be Trivially Bypassed**
   - File: `services/execution-sandbox/src/execution_sandbox/security.py`, lines 21-100
   - Regex-based blocklist has fundamental bypass vectors: encoding bypass (language-level exec not caught), path aliasing (`/usr///bin/rm`), and overly broad `find -exec` blocking that would break the evaluation engine's compilation layer.
   - Fix: Replace regex blocking with a whitelist approach — only allow known safe command prefixes.

3. **C-3. No Optimistic Concurrency Guard on Ledger Version During Commit**
   - File: `services/world-state-ledger/src/world_state_ledger/state_manager.py`, lines 130-239
   - Between reading current state and writing a new ledger row, another proposal could be committed. No `WHERE version = expected` or `SELECT ... FOR UPDATE` guard exists. `OptimisticConcurrencyError` class exists but is never raised.
   - Fix: Add a version-check guard to the ledger insert using database-level locking.

### High (6)

4. **H-1. LLMClient Not Used as Async Context Manager — Resource Leak Risk**
   - File: `services/coding-agent/src/coding_agent/temporal/activities.py`, lines 40-55
   - `LLMClient` lacks `__aenter__`/`__aexit__` and `close()` is not reliably called, leaking httpx connection pools.

5. **H-2. EventSubscriber Retry Counter Grows Unbounded in Memory**
   - File: `libs/architect-events/src/architect_events/subscriber.py`, line 52
   - `_retry_counts: dict[str, int]` grows without bound for failing messages that never exceed max retries.

6. **H-3. DockerExecutor Uses Deprecated `get_event_loop().run_in_executor`**
   - File: `services/execution-sandbox/src/execution_sandbox/docker_executor.py`, lines 63-297
   - Python 3.12+ deprecates `asyncio.get_event_loop()`. Should use `asyncio.to_thread()`.

7. **H-4. Hardcoded Task/Agent IDs in Temporal Activity**
   - File: `services/coding-agent/src/coding_agent/temporal/activities.py`, lines 119-120
   - Placeholder IDs `"task-temporal00000"` defeat audit trail and tracing.

8. **H-5. TaskScheduler Directly Mutates Internal Graph State**
   - File: `services/task-graph-engine/src/task_graph_engine/scheduler.py`, lines 107-236
   - Scheduler accesses `self._dag._graph.nodes[task_id]["task"]` directly, breaking encapsulation.

9. **H-6. API Gateway Module-Level Singletons Prevent Testing**
   - File: `apps/api-gateway/src/api_gateway/__init__.py`, lines 30-31
   - Config and `ServiceClient` created at module import time, making test configuration and mocking difficult.

### Medium (11)

10. **M-1. Token Usage Accumulation Bug** — `coding_agent/agent.py` line 84 uses `+=` instead of `=`, double-counting planning tokens.
11. **M-2. Evaluator Creates Reports Twice** — Wasteful intermediate frozen object in `evaluation_engine/evaluator.py`.
12. **M-3. UUID Collision Risk with Truncated Hex** — Only 48 bits of entropy in `_prefixed_uuid`, collision risk at ~17M IDs.
13. **M-4. `assert` Used for Production Preconditions** — `architect_events/dlq.py` and `subscriber.py` use `assert` stripped by `-O`.
14. **M-5. TaskRepository Uses String Literals Instead of Enums** — `task_repo.py` compares against raw strings instead of `StatusEnum`.
15. **M-6. StateCache 30s TTL Too Short** — Thundering herd risk with no stampede prevention.
16. **M-7. TaskDecomposer Doesn't Handle Markdown-Fenced JSON** — LLM responses often wrap JSON in code fences.
17. **M-8. Inconsistent Logging (stdlib vs structlog)** — `architect-events`, `architect-llm`, and `spec-engine` use `logging.getLogger`.
18. **M-9. Excessive `# type: ignore` in TreeSitterIndexer** — 100+ type ignores defeat type checking.
19. **M-10. SandboxClient Eager HTTP Client Creation** — Connection pool created before use, no lazy initialization.
20. **M-11. ServiceClient 30s Timeout Too Low** — LLM-backed operations can take 60-120s.

### Low (12)

21. **L-1.** `str_strip_whitespace=True` on `ArchitectBase` may corrupt source code content fields.
22. **L-2.** `CostTracker.check_budget` logs warnings on every call above threshold (no dedup).
23. **L-3.** `_resolve_sandbox_path` uses string prefix matching instead of `Path.is_relative_to()`.
24. **L-4.** `LLMClient.generate` imports private `_resolve_pricing` inside hot path.
25. **L-5.** `Proposal` model has `verdict` fields that conflict with frozen base semantics (misleading).
26. **L-6.** `EventLog.append` commits in its own session, breaking transactional composition.
27. **L-7.** `ComplexityScorer` has unexplained magic numbers for weights and thresholds.
28. **L-8.** Test factories return `dict[str, Any]` instead of typed domain models.
29. **L-9.** CORS allows all methods and headers (fine for dev, not for production).
30. **L-10.** `BaseRepository.list_all` has no maximum limit guard.
31. **L-11.** `NetworkPolicy.allowed_hosts` duplicated between models and security module.
32. **L-12.** `WorldState` mutable but sub-states frozen — confusing for developers.

---

## Architecture Findings

### Critical (3)

1. **A-C1. Temporal Activities Use Module-Level Globals (Service Locator Anti-Pattern)**
   - File: `services/world-state-ledger/src/world_state_ledger/temporal/activities.py`
   - Module-level `_state_manager: Any = None` with `global` mutations breaks concurrent testing, loses static type checking, creates temporal coupling.
   - Fix: Use Temporal's dataclass-based activity class pattern for dependency injection.

2. **A-C2. Scheduler Mutates DAG Internals Directly** (same as H-5 above)
   - File: `services/task-graph-engine/src/task_graph_engine/scheduler.py`

3. **A-C3. Duplicate Mutation Application Logic** (same as C-1 above)

### High (5)

4. **A-H1. WorldState is Mutable, Breaking Immutability Convention**
   - `WorldState` extends `MutableBase` while all other domain models use frozen `ArchitectBase`. The `_apply_mutations` method already does copy-on-write via model_dump/model_validate, making mutation unnecessary.

5. **A-H2. TaskDAG is Process-Local, No Persistence**
   - File: `services/task-graph-engine/src/task_graph_engine/api/dependencies.py`, line 83
   - If the process restarts, the entire graph is lost. `TaskRepository` exists but DAG structure (edges) is never persisted.

6. **A-H3. No API Versioning on Phase 1 Services**
   - Phase 1 uses bare paths (`/state`, `/tasks`); Phase 2 uses `/api/v1/`. Inconsistent and prevents evolution.

7. **A-H4. Untyped `dict[str, Any]` Pervasive in Protocol Interfaces**
   - File: `libs/architect-common/src/architect_common/interfaces.py`
   - All Protocol methods return `dict[str, Any]`, defeating structural subtyping benefits.

8. **A-H5. Missing Foreign Key Constraints**
   - `Task.assigned_agent`, `Proposal.agent_id`, `Proposal.task_id`, and `EventLog` fields lack FK constraints, allowing orphaned references.

### Medium (11)

9. **A-M1.** Inconsistent `tool.uv.sources` declarations across service `pyproject.toml` files.
10. **A-M2.** In-memory `_run_store` in coding agent API routes — volatile, no coordination.
11. **A-M3.** Execution sandbox missing Temporal integration (only service without `temporal/` sub-package).
12. **A-M4.** Gateway raw `raise_for_status()` error handling — no structured error transformation.
13. **A-M5.** Missing pagination metadata on `/events` endpoint.
14. **A-M6.** Sandbox client default port `8002` mismatches actual port `8007`.
15. **A-M7.** ORM models use plain `Text` columns for enum values — no database-level enforcement.
16. **A-M8.** WorldStateLedger stores full snapshots instead of deltas — storage scalability concern.
17. **A-M9.** No Alembic migration files present — deployment relies on `create_all()`.
18. **A-M10.** Module-level `app = create_app()` instantiation in all services — side effects on import.
19. **A-M11.** Temporal workflows use string activity names instead of function references.

### Low (8)

20. **A-L1.** Health endpoints return `HEALTHY` unconditionally — useless for readiness gates.
21. **A-L2.** `codebase-comprehension` missing `architect-events` dependency.
22. **A-L3.** `temporalio` not explicitly declared in WSL's `pyproject.toml`.
23. **A-L4.** Evaluator creates frozen reports twice (clarity issue).
24. **A-L5.** Missing `LedgerRepository` — StateManager uses raw SQLAlchemy queries.
25. **A-L6.** Overly aggressive command blocklist (blocks legitimate `find -exec`, `eval`).
26. **A-L7.** `budget_status` variable may be unbound in `TaskOrchestrationWorkflow`.
27. **A-L8.** Shared testing library (`architect-testing`) underutilized by service tests.

---

## Critical Issues for Phase 2 Context

These findings should inform the Security and Performance reviews:

### Security-Relevant
- **C-2**: Command filter bypass vectors in execution sandbox
- **C-3**: Missing OCC guard allows concurrent state corruption
- **A-H5**: Missing FK constraints allow referential integrity violations
- **L-3**: Path validation bypass via string prefix matching
- **L-9**: Overly permissive CORS configuration

### Performance-Relevant
- **H-2**: Unbounded retry counter memory growth
- **M-6**: 30s cache TTL causes thundering herd
- **M-11**: 30s gateway timeout too low for LLM operations
- **A-M8**: Full snapshot storage instead of delta-based ledger
- **A-H2**: Process-local TaskDAG with no persistence (crash recovery)
- **H-3**: Deprecated asyncio patterns may cause performance warnings
