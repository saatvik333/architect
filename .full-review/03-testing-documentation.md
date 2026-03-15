# Phase 3: Testing & Documentation Review

## Test Coverage Findings

### Critical (4)

1. **T-C1. Zero Temporal Workflow/Activity Tests**
   - 17 temporal files across 7 services with no test coverage. Workflows orchestrate the entire pipeline.
   - Fix: Add `test_workflows.py` using `temporalio.testing.WorkflowEnvironment`. Mock activities, verify retry logic and ordering.

2. **T-C2. No Concurrency Tests for `validate_and_commit`**
   - No test simulates two proposals racing against the same state field. Related to S-C4/P-M1.
   - Fix: Integration test submitting concurrent proposals targeting the same field, verify only one succeeds.

3. **T-C3. Phase 1 Service API Routes Have No Tests**
   - WSL, task-graph, execution-sandbox, evaluation-engine, coding-agent all lack route tests. Phase 2 services DO have them.
   - Fix: Add `test_routes.py` for all 5 Phase 1 services using FastAPI `TestClient`.

4. **T-S1. No Adversarial Bypass Tests for Command Filter**
   - Tests check patterns individually but not bypass techniques: variable expansion, backtick substitution, language-level exec, heredoc, command chaining.
   - Fix: Parametrized tests covering `CMD=rm; $CMD`, `` `rm -rf /` ``, `python -c "..."`, `bash -c "..."`, etc.

### High (7)

5. **T-H1.** `EventPublisher.publish` has no unit tests — critical infrastructure component.
6. **T-H2.** `EventSubscriber._read_loop` retry/DLQ logic never exercised under realistic conditions.
7. **T-H3.** `SandboxClient` (HTTP client) has no tests — error handling for timeouts untested.
8. **T-H4.** `architect-db` repositories minimally tested — 7 repos, 1 test file.
9. **T-H5.** `rate_limiter.py` has no tests — concurrency-sensitive token bucket logic untested.
10. **T-E1.** No concurrent access tests for `TaskScheduler` — race condition on `schedule_next` + `mark_running`.
11. **T-P1.** No load/performance tests whatsoever — no locust, k6, or benchmark tests.

### Medium (5)

12. **T-M1.** `CodeGenerator._parse_files` not tested with adversarial/malformed LLM output.
13. **T-M2.** Dashboard missing tests for 4 components and 2 hooks.
14. **T-M3.** `libs/architect-common` untested modules: `errors.py`, `enums.py`, `interfaces.py`, `logging.py`.
15. **T-E5.** `_apply_mutations` not tested with deeply nested or invalid dot-paths.
16. **T-S3.** No prompt injection tests for coding agent (adversarial spec descriptions).

### Low (3)

17. **T-L1.** Over-reliance on mocks in WSL tests — directly patches internal session factory.
18. **T-L2.** Frozen model tests use try/except instead of `pytest.raises`.
19. **T-L3.** Missing mock call argument verification in several tests.

### Testing Strengths
- Behavioral testing pattern (test outcomes, not implementations)
- Good assertion quality with specific checks
- Proper async patterns with `asyncio_mode=auto`
- Shared factory/mock infrastructure in `architect-testing`
- PromptFoo regression testing with 4 suites including adversarial inputs
- Low flaky test risk — no `time.sleep`, no network-dependent unit tests

### Test Pyramid Assessment
- **Unit:** 66 files — solid foundation
- **Integration:** 1 file — critical gap
- **E2E:** 3 files — skip when infra unavailable, likely never run in CI
- **Contract:** None — no pact/contract tests between services
- **Load/Perf:** None — missing entirely
- **PromptFoo:** 4 suites — good LLM regression coverage

---

## Documentation Findings

### Critical (2)

1. **D-C1. Port Numbers Incorrect in `service-operations.md`**
   - Health check curl examples use wrong ports for all 5 Phase 1 services.
   - Fix: Correct to WSL=8001, TGE=8003, Sandbox=8007, Eval=8008, CodingAgent=8009.

2. **D-C2. No Authentication/Authorization Documentation**
   - No design doc, ADR, or "TODO" section for the planned auth model. All APIs are publicly accessible.
   - Fix: Create ADR-005 for planned auth model. Add "Security Considerations" to API reference.

### High (2)

3. **D-H1. No Docker Socket Security Runbook**
   - Sandbox uses Docker socket mount but no documentation covers security implications, permissions, or alternatives (rootless Docker, DinD).
   - Fix: Create `docs/runbooks/docker-security.md`.

4. **D-H2. No Deployment Guide**
   - Only local dev setup documented. No cloud deployment, production config, secrets management, or CI/CD docs.
   - Fix: Create `docs/runbooks/deployment.md`.

### Medium (11)

5. **D-M1.** Eval Engine port wrong in `phase-2-design.md` (says 8004, should be 8008).
6. **D-M2.** Docker image references say `postgres:16` but actual is `pgvector/pgvector:pg16`.
7. **D-M3.** No ADR for delta-based ledger migration decision.
8. **D-M4.** No horizontal scaling documentation.
9. **D-M5.** Semantic search endpoints missing from Gateway route table in API docs.
10. **D-M6.** `GET /api/v1/tasks` (list all) missing from Gateway route table.
11. **D-M7.** Missing ADRs for dual pub-sub (NATS + Redis Streams) and proposal-gated mutation model.
12. **D-M8.** README missing `make run-all`, `make stop-all`, and other commands.
13. **D-M9.** No quickstart for running the full system with `make run-all`.
14. **D-M10.** No migration guide for breaking changes between versions.
15. **D-M11.** Codebase Comprehension undocumented components (tree-sitter indexer, embeddings, vector store) in ARCHITECTURE.md.

### Low (11)

16. **D-L1.** Stale line counts in ARCHITECTURE.md.
17. **D-L2.** Dashboard workspace membership unclear in README.
18. **D-L3.** Package count confusion (14 vs 15 services).
19. **D-L4.** `GET /api/v1/proposals` not in Gateway route table.
20. **D-L5.** Some route functions lack rich docstrings for OpenAPI generation.
21. **D-L6.** Complexity scorer weights lack inline rationale.
22. **D-L7.** Missing Phase 2 data flow diagram.
23. **D-L8.** Hardcoded test counts (576) will become stale.
24. **D-L9.** Phase labels missing from changelog entries.
25. **D-L10.** Typo "miigation" in SECURITY.md.
26. **D-L11.** CLAUDE.md missing several Makefile targets.

### Documentation Strengths
- Comprehensive README, ARCHITECTURE.md, CONTRIBUTING.md
- 4 ADRs for key architectural decisions
- Detailed phase design documents
- Multiple operational runbooks
- Module-level and class-level docstrings throughout Python code
- CHANGELOG follows Keep a Changelog format
- PromptFoo testing runbook
