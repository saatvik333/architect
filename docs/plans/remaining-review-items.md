# Remaining Review Items — Implementation Plan

## Overview

After the comprehensive code review (~199 findings), ~120 were resolved in commit `13ad956`. This document tracks the remaining ~79 items organized into implementation phases with effort estimates and priorities.

### What Was Resolved

The resolution commit addressed:

- **Security:** Sandbox allowlist (S-C1), path validation fix (S-C3), OCC guard (S-C4), CORS restriction (S-H2), FK constraints (S-H4), tar slip fix (S-H6), env var injection block (S-H7), security scans now blocking (S-L1/O-H1)
- **Architecture:** Temporal DI refactor (A-C1), DAG encapsulation (A-C2/H-5), mutation dedup (C-1/A-C3), factory pattern for all services (A-M10), structlog standardization (F-M2)
- **Performance:** Cache stampede prevention (P-C4), bounded retry counter (P-C2/H-2), deprecated asyncio fix (P-H5/F-M1), gateway timeout increase (P-H7), bounded session store, DB indexes (P-H1)
- **Testing:** 96 new tests — 5 route test suites (T-C3), adversarial security tests (T-S1), EventPublisher/Subscriber tests (T-H1/T-H2), rate limiter tests (T-H5)
- **CI/CD:** Pinned container images (O-H2), coverage threshold (O-M1), Dockerfile pinning (O-M7)
- **Documentation:** Port corrections (D-C1), stale counts, route table updates, README additions
- **Frontend:** Error boundary (F-M6), AbortController in polling (F-M7)

### What Remains

~79 findings across security, performance, testing, observability, and code quality. These are organized below into five implementation phases spanning ~12.5 weeks.

---

## Phase A: Security Hardening (Week 1-2) — COMPLETED

### A1. API Key Authentication (S-C2, CVSS 9.1)

- **Priority:** P0 — blocks production deployment
- **Effort:** Medium (2-3 days)
- **Scope:**
  - Add `X-API-Key` header validation middleware to API gateway
  - Store allowed keys in environment variable (comma-separated)
  - Return 401 on missing/invalid key
  - Add `ARCHITECT_API_KEYS` to `.env.example`
  - Bypass auth for `/health` endpoint
  - Update all gateway tests to include API key header
- **Files:** `apps/api-gateway/src/api_gateway/__init__.py`, `apps/api-gateway/src/api_gateway/config.py`
- **ADR:** `docs/architecture/adr-005-api-authentication.md` (to be created alongside)

### A2. Redis Authentication (S-H3, O-H4)

- **Priority:** P0
- **Effort:** Small (half day)
- **Scope:**
  - Add `--requirepass` to Redis in docker-compose
  - Add `REDIS_PASSWORD` env var to `ArchitectConfig`
  - Update all Redis client constructors to use password
  - Update `StateCache`, `EventPublisher`, `EventSubscriber`
- **Files:** `infra/docker-compose.yml`, `libs/architect-common/src/architect_common/config.py`, all Redis client call sites

### A3. Prompt Injection Mitigation (S-H1)

- **Priority:** P1
- **Effort:** Medium (2 days)
- **Scope:**
  - Add input sanitization for spec fields before LLM prompt construction
  - Use structured tool-use pattern instead of raw string concatenation
  - Add post-generation security scan (check generated code for suspicious patterns)
  - Add adversarial prompt injection test cases (extends T-S3)
- **Files:** `services/coding-agent/src/coding_agent/coder.py`, `services/spec-engine/src/spec_engine/parser.py`

### A4. Docker Socket Security (S-H5, O-H9)

- **Priority:** P1
- **Effort:** Large (1 week)
- **Scope:**
  - Evaluate Docker socket proxy (e.g., Tecnativa/docker-socket-proxy)
  - Restrict allowed Docker API calls to: create, start, stop, remove, exec, inspect
  - Block: image pull, volume mount, network create, privileged containers
  - Alternative: evaluate rootless Docker or Docker-in-Docker
  - Create `docs/runbooks/docker-security.md` (D-H1)
- **Files:** `infra/docker-compose.yml`, `services/execution-sandbox/src/execution_sandbox/docker_executor.py`

### A5. Hardcoded Credentials Removal (O-H3, S-M2, S-M5)

- **Priority:** P1
- **Effort:** Small (1 day)
- **Scope:**
  - Remove default passwords from `docker-compose.yml` (Postgres, Temporal)
  - Require explicit env vars for all credentials (fail fast if missing)
  - Remove `architect_dev` defaults from `.env.example` — use placeholder instructions instead
  - Update `dev-setup.sh` to prompt for or generate credentials
- **Files:** `infra/docker-compose.yml`, `.env.example`, `scripts/dev-setup.sh`

### A6. Security Headers & Rate Limiting (S-M1, S-M3, S-M7)

- **Priority:** P2
- **Effort:** Medium (1-2 days)
- **Scope:**
  - Wire `rate_limit_per_minute` config into actual middleware (use `slowapi` or custom token bucket)
  - Rate limit by IP or API key; return 429 with `Retry-After` header
  - Add security headers middleware: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`
  - Add request body size limits on API endpoints
- **Files:** `apps/api-gateway/src/api_gateway/__init__.py`

---

## Phase B: Data Integrity & Performance (Week 2-3) — COMPLETED

### B1. Delta-Based Ledger Storage (P-C1, A-M8)

- **Priority:** P1 — current quadratic growth is unsustainable
- **Effort:** Large (1 week)
- **Scope:**
  - Change ledger rows to store mutation diffs instead of full snapshots
  - Add periodic full checkpoint rows (every N commits or on demand)
  - Add `reconstruct_state(version)` that replays diffs from last checkpoint
  - Migrate existing data: keep current rows as checkpoints
  - Update `StateManager.get_current()` and `get_version()` to use new format
  - Create ADR for the migration decision (D-M3)
- **Files:** `services/world-state-ledger/src/world_state_ledger/state_manager.py`, `libs/architect-db/` (new migration + model changes)

### B2. Persist Sandbox Sessions to DB (P-C3)

- **Priority:** P1
- **Effort:** Medium (2-3 days)
- **Scope:**
  - Add `SandboxSession` ORM model with container_id, status, created_at, last_active
  - On startup: query Docker for running ARCHITECT containers, reconcile with DB
  - On crash recovery: clean up orphaned containers
  - Replace process-local `_sessions` dict with DB-backed store
- **Files:** `services/execution-sandbox/src/execution_sandbox/docker_executor.py`, `libs/architect-db/` (new model + migration)

### B3. Horizontal Scheduler Scaling (P-C5)

- **Priority:** P2
- **Effort:** Large (1 week)
- **Scope:**
  - Move scheduling state (ready queue, running set) to Redis or Postgres
  - Use Redis SETNX or Postgres advisory locks for task claiming
  - Multiple scheduler instances can run without split-brain
  - Keep in-memory mode as fallback for single-instance deployments
  - Address scheduler race condition (P-H9) as part of this work
- **Files:** `services/task-graph-engine/src/task_graph_engine/scheduler.py`

### B4. ORM Enum Columns (A-M7)

- **Priority:** P2
- **Effort:** Small (1 day)
- **Scope:**
  - Replace `Text` columns storing enum values with proper `Enum` database columns
  - Create Alembic migration for the column type change
  - Update repository queries
- **Files:** `libs/architect-db/src/architect_db/models/`, new migration in `libs/architect-db/migrations/versions/`

### B5. Connection Pool Sizing (P-H2)

- **Priority:** P2
- **Effort:** Small (half day)
- **Scope:**
  - Audit pool_size across all 9 services (currently 10 max each = 90 vs Postgres default 100)
  - Reduce per-service pool to 5-8, or increase Postgres max_connections
  - Make pool_size configurable via env var
  - Increase Postgres memory limit from 512MB (P-M11/O-M6)
- **Files:** `libs/architect-db/src/architect_db/engine.py`, `infra/docker-compose.yml`

### B6. Additional Performance Items (P-H4, P-H6, P-H8, P-H10, P-H11)

- **Priority:** P2
- **Effort:** Medium (2-3 days)
- **Scope:**
  - **P-H4:** Bound IndexStore in-memory growth (max entries, LRU eviction)
  - **P-H6:** Make `container.stats()` call non-blocking or optional after command execution
  - **P-H8:** Run `model.encode()` via `asyncio.to_thread()` to unblock event loop
  - **P-H10:** Make cache update atomic with state commit (or invalidate on failure)
  - **P-H11:** Add `MAXLEN` to Redis Streams `XADD` calls to prevent unbounded growth
- **Files:** Various across `codebase_comprehension/`, `execution_sandbox/`, `world_state_ledger/`, `architect_events/`

---

## Phase C: Observability & Operations (Week 3-4) — COMPLETED

### C1. OpenTelemetry Tracing (O-H6)

- **Priority:** P1
- **Effort:** Large (1 week)
- **Scope:**
  - Add `opentelemetry-instrumentation-fastapi` to all services
  - Add `opentelemetry-instrumentation-sqlalchemy` for DB tracing
  - Add Temporal interceptor for workflow/activity tracing
  - Configure Jaeger or OTLP exporter in docker-compose
  - Add trace context propagation in `ServiceClient` and `EventPublisher`
- **Dependencies:** New packages: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`

### C2. Prometheus Metrics (O-H6)

- **Priority:** P1
- **Effort:** Medium (2-3 days)
- **Scope:**
  - Add `prometheus-fastapi-instrumentator` to all services
  - Add custom metrics: proposals/sec, eval pass rate, sandbox utilization, LLM token spend
  - Add Prometheus + Grafana to docker-compose
  - Create basic Grafana dashboard JSON
- **Dependencies:** `prometheus-fastapi-instrumentator`, `prometheus-client`

### C3. Deployment Pipeline (O-C1, O-C2)

- **Priority:** P1
- **Effort:** Large (1-2 weeks)
- **Scope:**
  - Create Kubernetes manifests or Docker Compose production overlay
  - Create GitHub Actions CD workflow with staging -> production promotion
  - Add manual approval gate for production
  - Create environment-specific configs (staging, production)
  - Document rollback procedure (O-H7)
  - Stop pushing mutable `latest` tags (O-H5)
- **Files:** New `infra/k8s/` or `infra/docker-compose.prod.yml`, `.github/workflows/deploy.yml`

### C4. Incident Response & Operational Runbooks (O-H8, D-H2)

- **Priority:** P2
- **Effort:** Small (1 day)
- **Scope:**
  - Create `docs/runbooks/incident-response.md` — how to check service health, read logs, restart services, rollback, common failure modes
  - Create `docs/runbooks/deployment.md` — cloud deployment, production config, secrets management
  - Document horizontal scaling architecture (D-M4)

---

## Phase D: Testing Gaps (Week 4-5)

### D1. Temporal Workflow Tests (T-C1)

- **Priority:** P1 — 17 temporal files with 0% test coverage
- **Effort:** Large (1 week)
- **Scope:**
  - Use `temporalio.testing.WorkflowEnvironment` for all 7 services with temporal sub-packages
  - Test: workflow execution, activity retry logic, signal handling, error propagation
  - Mock activities to test workflow orchestration logic in isolation
  - Target: at least 2-3 tests per workflow
  - Fix string-based activity references in workflows (F-M4/A-M11) as part of this work
- **Files:** New `tests/test_workflows.py` in:
  - `services/world-state-ledger/`
  - `services/task-graph-engine/`
  - `services/coding-agent/`
  - (and other services with temporal sub-packages)

### D2. Concurrency Tests for validate_and_commit (T-C2)

- **Priority:** P1
- **Effort:** Medium (2 days)
- **Scope:**
  - Integration test with real Postgres submitting 2 concurrent proposals targeting same field
  - Verify exactly one succeeds, other raises `OptimisticConcurrencyError`
  - Test with 5-10 concurrent proposals to verify no corruption
  - Also test the multi-session race window in validate_and_commit (P-M1)
- **Files:** `tests/integration/test_concurrent_proposals.py`

### D3. Load/Performance Tests (T-P1)

- **Priority:** P2
- **Effort:** Medium (2-3 days)
- **Scope:**
  - Add k6 or locust scripts for gateway endpoints
  - Measure: requests/sec, p99 latency, error rate under load
  - Test: 100 concurrent task submissions, 50 concurrent state reads
  - Verify cache stampede prevention under load
  - Document performance baselines
- **Files:** New `tests/load/` directory

### D4. Contract Tests

- **Priority:** P3
- **Effort:** Medium (3 days)
- **Scope:**
  - Add Pact or schema-based contract tests between gateway and services
  - Verify that service response schemas match what gateway expects
  - Run in CI

### D5. Remaining Unit Test Gaps (T-H3, T-H4, T-E1, T-M1-M5)

- **Priority:** P2
- **Effort:** Medium (3 days)
- **Scope:**
  - **T-H3:** SandboxClient HTTP error handling tests (timeouts, connection failures)
  - **T-H4:** Expand architect-db repository tests (7 repos, currently 1 test file)
  - **T-E1:** Concurrent access tests for TaskScheduler (race on `schedule_next` + `mark_running`)
  - **T-M1:** Test `CodeGenerator._parse_files` with adversarial/malformed LLM output
  - **T-M2:** Dashboard component tests (4 components, 2 hooks untested)
  - **T-M3:** Tests for `architect-common` modules: `errors.py`, `enums.py`, `interfaces.py`, `logging.py`
  - **T-M5/T-S3:** Prompt injection tests for coding agent (adversarial spec descriptions)
  - **T-E5:** Test `_apply_mutations` with deeply nested or invalid dot-paths

---

## Phase E: Code Quality & Modernization (Ongoing)

### E1. API Versioning (A-H3)

- **Priority:** P2
- **Effort:** Medium (2 days)
- **Scope:**
  - Add `/api/v1/` prefix to all Phase 1 service routes (currently bare paths)
  - Update gateway routing to match
  - Keep old routes as redirects temporarily for backward compatibility

### E2. Typed Protocol Interfaces (A-H4)

- **Priority:** P3
- **Effort:** Large (1 week)
- **Scope:**
  - Replace `dict[str, Any]` in Protocol methods with proper domain models
  - Update all implementations
  - This is a large refactor — do incrementally per service
- **Files:** `libs/architect-common/src/architect_common/interfaces.py` and all implementations

### E3. LLMClient Resource Management (H-1, F-M3)

- **Priority:** P2
- **Effort:** Small (1 day)
- **Scope:**
  - Add `__aenter__`/`__aexit__` to LLMClient for proper async context manager support
  - Ensure httpx connection pool is closed on exit
  - Update all call sites to use `async with`
  - Ensure Temporal activities reuse LLMClient across calls (F-M3 — rate limiter state + pool preservation)
- **Files:** `libs/architect-llm/src/architect_llm/client.py`, all call sites

### E4. TaskDAG Persistence (A-H2)

- **Priority:** P2
- **Effort:** Medium (2-3 days)
- **Scope:**
  - Persist DAG structure (nodes + edges) to database via TaskRepository
  - On process restart, reconstruct DAG from persisted data
  - Add startup reconciliation logic
- **Files:** `services/task-graph-engine/src/task_graph_engine/graph.py`, `libs/architect-db/src/architect_db/repositories/task_repo.py`

### E5. WorldState Immutability (A-H1)

- **Priority:** P3
- **Effort:** Small (half day)
- **Scope:**
  - Change `WorldState` to extend frozen `ArchitectBase` instead of `MutableBase`
  - The `_apply_mutations` already does copy-on-write via `model_dump()`/`model_validate()`, so mutation is unnecessary
  - Update any code that relies on mutability
- **Files:** `services/world-state-ledger/src/world_state_ledger/models.py`

### E6. Remaining Medium/Low Items

These items can be addressed opportunistically as part of nearby work:

| ID | Finding | Effort |
|---|---|---|
| M-1 | Token usage accumulation bug (`+=` instead of `=`) in `coding_agent/agent.py` | Tiny |
| M-7 | TaskDecomposer doesn't handle markdown-fenced JSON from LLMs | Small |
| M-9 | Excessive `# type: ignore` in TreeSitterIndexer | Medium |
| M-10 | SandboxClient eager HTTP client creation | Small |
| A-M1 | Inconsistent `tool.uv.sources` across `pyproject.toml` files | Small |
| A-M2 | In-memory `_run_store` in coding agent API routes | Small |
| A-M3 | Execution sandbox missing Temporal integration | Medium |
| A-M4 | Gateway raw `raise_for_status()` — no structured error transformation | Small |
| A-M5 | Missing pagination metadata on `/events` endpoint | Small |
| A-M9 | No Alembic migration files present (relies on `create_all()`) | Small |
| S-M4 | Unbounded in-memory session store in coding agent | Small |
| S-M6 | Information leakage via upstream error forwarding in gateway | Small |
| S-M8 | Container images use `latest` tags (remaining instances) | Small |
| P-M2 | Missing pagination on `get_by_task`, `get_by_verdict`, `get_pending` | Small |
| P-M3 | Missing index on `evaluation_reports.verdict` | Tiny |
| P-M4 | Unbounded audit log per sandbox session | Small |
| P-M5 | VectorStore creates separate connection pool | Small |
| P-M6 | Sequential file reads in `ASTIndexer.index_directory` | Medium |
| P-M7 | Unbatched bulk INSERT in VectorStore | Small |
| P-M8 | TokenBucketRateLimiter lock contention | Small |
| P-M9 | No lazy loading of React routes/heavy deps | Small |
| P-M10 | DAG layout recomputed every 3s poll cycle | Small |
| P-M12 | O(n*m) linear symbol search in IndexStore | Medium |
| O-M2 | Integration tests minimal — no Temporal or NATS in CI | Medium |
| O-M3 | E2E tests never run in CI | Medium |
| O-M4 | Sandbox image not built in CI/release pipeline | Small |
| O-M5 | Health check script has stale port mappings | Tiny |
| D-M1 | Eval Engine port wrong in `phase-2-design.md` | Tiny |
| D-M2 | Docker image references say `postgres:16` vs actual `pgvector/pgvector:pg16` | Tiny |
| D-M5 | Semantic search endpoints missing from Gateway route table | Tiny |
| D-M6 | `GET /api/v1/tasks` missing from Gateway route table | Tiny |
| D-M7 | Missing ADRs for dual pub-sub and proposal-gated mutation model | Medium |
| D-M8 | README missing some Makefile targets | Tiny |
| D-M9 | No quickstart for running the full system | Small |
| D-M10 | No migration guide for breaking changes | Small |
| D-M11 | Codebase Comprehension undocumented in ARCHITECTURE.md | Small |

### E7. Low Priority / Backlog Items

These are minor code smells, documentation typos, and cosmetic improvements (59 items from original review). Address during regular maintenance or as drive-by fixes:

- `str_strip_whitespace=True` may corrupt source code fields (L-1)
- `CostTracker.check_budget` log spam (L-2)
- Private import in hot path (L-4/F-L6)
- `Proposal` verdict field confusing with frozen semantics (L-5)
- `EventLog.append` breaks transactional composition (L-6)
- `ComplexityScorer` magic numbers (L-7)
- Test factories return untyped dicts (L-8)
- `BaseRepository.list_all` no max limit (L-10)
- Duplicated `NetworkPolicy.allowed_hosts` (L-11)
- Dead `TypeVar` alongside PEP 695 syntax (F-L1)
- No `match/case` usage (F-L2)
- Inconsistent lifespan return types (F-L3)
- `dir()` check for variable existence in workflow (F-L4)
- Route DTOs inherit `BaseModel` instead of shared base (F-L5)
- Potentially unstable NATS API usage (F-L7)
- TypeScript target could be ES2022+ (F-L8)
- Additional ruff lint rules available (F-L9)
- Health endpoints return HEALTHY unconditionally (A-L1)
- Missing package dependencies (A-L2, A-L3)
- Unbound `budget_status` variable in workflow (A-L7)
- `architect-testing` lib underutilized (A-L8)
- No log sanitization (S-L2)
- `find -exec` blocklist overly broad (S-L3)
- Missing cookie attributes for future auth (S-L4)
- No request/correlation ID in responses (S-L5)
- Dashboard JS dependencies not audited (S-L6)
- No Redis connection pool sharing (P-L1)
- Polling without backoff on errors in dashboard (P-L2)
- TreeSitter parser created per file (P-L3)
- `_resolve_pricing` linear scan (P-L4)
- Duplicate token estimation (P-L5)
- Redundant proposal DB reads (P-L6)
- Over-reliance on mocks in WSL tests (T-L1)
- `try/except` instead of `pytest.raises` (T-L2)
- Missing mock call argument verification (T-L3)
- No container image scanning in CI (O-L1)
- `dev-setup.sh` missing pre-push hook install (O-L2)
- No multi-arch container builds (O-L3)
- Various documentation typos and stale references (D-L1 through D-L11)

---

## Summary

| Phase | Items | Effort | Priority |
|-------|-------|--------|----------|
| A: Security | 6 | ~2.5 weeks | P0-P2 |
| B: Data & Perf | 6 | ~3 weeks | P1-P2 |
| C: Observability | 4 | ~3 weeks | P1-P2 |
| D: Testing | 5 | ~2.5 weeks | P1-P3 |
| E: Code Quality | 7 groups | ~2 weeks | P2-P3 |
| **Total** | **28 work items + backlog** | **~13 weeks** | |

*Note: Effort estimates assume a single developer. Many items can be parallelized across 2-3 developers, reducing wall-clock time to ~5-6 weeks.*

---

## Recommended Execution Order

1. **A1 + A2** (API key auth + Redis auth) — unblocks any external access; P0 blockers
2. **A5** (hardcoded credentials) — quick win, complements auth work
3. **D1** (Temporal workflow tests) — builds confidence for subsequent refactors
4. **B1** (delta-based ledger) — prevents storage scaling issues early
5. **C1 + C2** (tracing + metrics) — enables monitoring before production
6. **A3 + A4** (prompt injection + Docker socket) — hardens security layer
7. **D2** (concurrency tests) — validates OCC guard under real contention
8. **B2 + B3** (sandbox persistence + scheduler scaling) — resilience improvements
9. **C3** (deployment pipeline) — enables actual deployments to staging/prod
10. **A6** (rate limiting + security headers) — production hardening
11. **B5 + B6** (connection pools + misc performance) — capacity planning
12. **E1 + E3 + E4** (API versioning + LLM resource mgmt + DAG persistence)
13. **C4 + D3** (runbooks + load tests) — operational readiness
14. **D4 + D5** (contract tests + remaining unit tests) — test coverage completion
15. Everything else as capacity allows

---

## Tracking

Each item should be converted to a GitHub issue with:
- The phase + item ID as a label (e.g., `phase-a`, `A1`)
- The priority label (`P0`, `P1`, `P2`, `P3`)
- The effort estimate in the description
- Links to the relevant review finding IDs from `.full-review/`

Progress updates should be added to this document as items are completed.

---

*Generated from `.full-review/05-final-report.md` and phase reports 01-04. Review date: 2026-03-15.*
