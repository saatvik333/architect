# Phase 2: Security & Performance Review

## Security Findings

### Critical (4)

1. **S-C1. Sandbox Command Filter Bypass via Shell Metacharacter Encoding** (CVSS 9.8, CWE-78)
   - File: `services/execution-sandbox/src/execution_sandbox/security.py`, lines 21-100
   - Regex blocklist bypassable via hex/octal encoding (`$'\x72\x6d'`), variable expansion (`R=rm; $R`), language-level exec (`python3 -c`), path aliasing (`/usr/bin/env rm`), and wildcard insertion (`r?m`).
   - Fix: Replace blocklist with allowlist of permitted binaries using `shlex.split()` parsing. Consider `execve` with explicit `argv` instead of `sh -c`.

2. **S-C2. No Authentication or Authorization on Any API Endpoint** (CVSS 9.1, CWE-306)
   - All endpoints across gateway, sandbox, coding agent, WSL, task graph, spec engine, router, codebase comprehension, and agent bus are completely unauthenticated.
   - `rate_limit_per_minute` config field exists but is never wired into middleware.
   - Fix: Add API key auth to gateway, implement service-to-service mTLS or signed JWT.

3. **S-C3. Path Validation Bypass via String Prefix Matching** (CVSS 8.6, CWE-22)
   - File: `services/execution-sandbox/src/execution_sandbox/security.py`, lines 164, 176
   - `str(resolved).startswith(str(workspace_root))` passes for `/workspace-evil/` when workspace is `/workspace`.
   - Fix: Use `Path.is_relative_to()` (Python 3.9+).

4. **S-C4. Missing OCC Guard Allows Concurrent State Corruption** (CVSS 8.1, CWE-362)
   - File: `services/world-state-ledger/src/world_state_ledger/state_manager.py`, lines 130-239
   - Read-modify-write across multiple sessions with no locking. Two concurrent proposals can both pass validation and commit, overwriting each other.
   - Fix: Use `SELECT ... FOR UPDATE` within a single transaction.

### High (7)

5. **S-H1. Prompt Injection via Untrusted Spec/Codebase Context** (CVSS 8.2, CWE-77)
   - Files: `coding_agent/context_builder.py`, `coding_agent/coder.py`, `spec_engine/parser.py`
   - User-provided spec fields and codebase content concatenated directly into LLM prompts. Attack chain: controlled spec -> prompt injection -> malicious code generation -> sandbox execution.
   - Fix: Sanitize inputs, use structured tool-use, add post-generation security scan.

6. **S-H2. CORS Allows All Methods and All Headers** (CVSS 7.5, CWE-942)
   - File: `apps/api-gateway/src/api_gateway/__init__.py`, lines 49-55
   - `allow_methods=["*"]` + `allow_headers=["*"]` + `allow_credentials=True`.
   - Fix: Restrict to specific methods and headers.

7. **S-H3. Redis Connections Have No Authentication** (CVSS 7.5, CWE-287)
   - Redis runs without `--requirepass`. Default config has empty password.
   - Fix: Add `--requirepass` to Redis config, set password in env vars.

8. **S-H4. Missing FK Constraints Allow Referential Integrity Violations** (CVSS 7.2, CWE-20)
   - `proposals.task_id`, `proposals.agent_id`, `event_log` columns all lack FK constraints.
   - Fix: Add ForeignKey constraints in migration.

9. **S-H5. Docker Socket Access Grants Host-Level Privilege Escalation** (CVSS 7.8, CWE-250)
   - Sandbox service connects to `/var/run/docker.sock`. Compromise = host root access.
   - Fix: Use Docker socket proxy, restrict API calls, consider rootless Docker.

10. **S-H6. Tar Slip Vulnerability in Sandbox File Read** (CVSS 7.5, CWE-22)
    - File: `execution_sandbox/docker_executor.py`, lines 257-264
    - Tar member names not validated for `../` traversal.
    - Fix: Validate member names, reject paths with `..` components.

11. **S-H7. Sandbox `environment_vars` Injection** (CVSS 7.4, CWE-78)
    - File: `execution_sandbox/resource_limits.py`, lines 39-43
    - User-controlled env vars merged without validation. Can inject `LD_PRELOAD`, `PYTHONPATH`, etc.
    - Fix: Block dangerous env var names, validate format.

### Medium (8)

12. **S-M1.** No rate limiting enforced on API gateway (CWE-770, CVSS 6.5)
13. **S-M2.** Hardcoded default credentials in docker-compose and config (CWE-798, CVSS 6.1)
14. **S-M3.** No security headers (CSP, HSTS, X-Frame-Options) on any response (CWE-693, CVSS 5.3)
15. **S-M4.** Unbounded in-memory session store in coding agent (CWE-400, CVSS 5.3)
16. **S-M5.** Temporal password hardcoded in docker-compose (CWE-798, CVSS 5.9)
17. **S-M6.** Information leakage via upstream error forwarding in gateway (CWE-209, CVSS 5.3)
18. **S-M7.** Missing input size limits on API request bodies (CWE-400, CVSS 5.3)
19. **S-M8.** Container images use `latest` tags — supply chain risk (CWE-829, CVSS 5.0)

### Low (6)

20. **S-L1.** Bandit/pip-audit scans non-blocking in CI (`|| true`)
21. **S-L2.** No log sanitization for structured log fields (CWE-117)
22. **S-L3.** `find -exec` blocklist overly broad
23. **S-L4.** Missing `Secure`/`HttpOnly` cookie attributes for future auth (CWE-614)
24. **S-L5.** No request ID/correlation ID in API responses (CWE-778)
25. **S-L6.** Dashboard JS dependencies not audited (no lock file scanning)

### Positive Security Observations
- `SecretStr` used for credentials, preventing accidental logging
- Detailed custom seccomp profile blocking dangerous syscalls
- Container hardening: read-only rootfs, dropped capabilities, no-new-privileges, non-root user, PID/memory limits
- Secret detection patterns in sandbox (`_SUSPICIOUS_FILE_PATTERNS`)
- Git path traversal protection uses `Path.relative_to()` correctly
- `uv.lock` provides deterministic dependency resolution

---

## Performance Findings

### Critical (5)

1. **P-C1. Full Snapshot Storage in WorldStateLedger — Quadratic Growth**
   - File: `state_manager.py`, lines 192-199
   - Every commit stores entire WorldState JSON (~2-5 MB for medium codebases). At 100 proposals/day = 200-500 MB/day.
   - Fix: Switch to delta-based storage with periodic full checkpoints.

2. **P-C2. Unbounded `_retry_counts` Dict in EventSubscriber — OOM Risk**
   - File: `architect_events/subscriber.py`, line 52
   - Only cleaned on success or max retries. Intermittent failures leave orphan entries.
   - Fix: Use TTL-based cache or `OrderedDict` with size bounds.

3. **P-C3. Process-Local `_sessions` in DockerExecutor — Orphaned Containers**
   - File: `docker_executor.py`, line 44
   - Process restart loses session tracking. Docker containers keep running.
   - Fix: Persist to DB, add startup reconciliation.

4. **P-C4. 30-Second Cache TTL Causes Thundering Herd**
   - File: `cache.py`, lines 38-47
   - All readers miss simultaneously when TTL expires.
   - Fix: Probabilistic early expiration + longer TTL (300s) with write-through.

5. **P-C5. Single-Process Scheduler Cannot Scale Horizontally**
   - File: `scheduler.py`
   - Entire DAG and completed-set in memory. Multiple instances = split-brain.
   - Fix: Move scheduling state to Redis/Postgres, use Temporal for orchestration.

### High (11)

6. **P-H1.** Missing composite index on `proposals(verdict, created_at)` — full table scan on `get_pending()`.
7. **P-H2.** Connection pool too small (10 max * 9 services = 90, Postgres default 100).
8. **P-H3.** Process-local TaskDAG — crash recovery loss.
9. **P-H4.** In-memory IndexStore in codebase comprehension — unbounded growth.
10. **P-H5.** Deprecated `asyncio.get_event_loop().run_in_executor` in 9 locations.
11. **P-H6.** Blocking `container.stats(stream=False)` after every command (1-3s block).
12. **P-H7.** Gateway 30s timeout too low for LLM operations (60-120s needed).
13. **P-H8.** Synchronous `model.encode()` blocks event loop in embeddings.
14. **P-H9.** Race condition in `schedule_next` + `mark_running` — two agents can claim same task.
15. **P-H10.** Non-atomic cache update after commit — stale data window on crash.
16. **P-H11.** Redis Streams `XADD` without `MAXLEN` — unbounded memory growth.

### Medium (12)

17. **P-M1.** `validate_and_commit` opens 4 separate sessions — race condition window.
18. **P-M2.** Missing pagination on `get_by_task`, `get_by_verdict`, `get_pending`.
19. **P-M3.** Missing index on `evaluation_reports.verdict`.
20. **P-M4.** Unbounded audit log per sandbox session (tens of MB).
21. **P-M5.** VectorStore creates separate connection pool from service engine.
22. **P-M6.** Sequential file reads in `ASTIndexer.index_directory`.
23. **P-M7.** Unbatched bulk INSERT in VectorStore for large indexing jobs.
24. **P-M8.** TokenBucketRateLimiter lock contention under concurrency.
25. **P-M9.** No lazy loading of React routes/heavy deps (@xyflow, dagre).
26. **P-M10.** DAG layout recomputed every 3s poll cycle (new array reference).
27. **P-M11.** Postgres 512MB memory limit too low for pgvector + JSONB + 100 connections.
28. **P-M12.** O(n*m) linear symbol search in IndexStore.

### Low (6)

29. **P-L1.** No Redis connection pool sharing within services.
30. **P-L2.** Polling continues without backoff on errors in dashboard.
31. **P-L3.** TreeSitter parser created per file instead of cached per language.
32. **P-L4.** `_resolve_pricing` linear scan on every LLM call.
33. **P-L5.** Duplicate token estimation in `LLMClient.generate`.
34. **P-L6.** Redundant proposal DB reads in `validate_and_commit`.

---

## Critical Issues for Phase 3 Context

### Testing Implications
- **S-C1, S-C2, S-C3**: Security-critical paths in sandbox, auth, and path validation need dedicated security test suites
- **S-H1**: Prompt injection scenarios need adversarial test cases
- **P-C5, P-H9**: Race conditions in scheduler need concurrent test scenarios
- **P-C4**: Cache stampede behavior needs load test verification

### Documentation Implications
- **S-C2**: Authentication model needs to be documented before implementation
- **S-H5**: Docker socket security model needs runbook documentation
- **P-C1**: Delta-based ledger migration needs ADR
- **P-C5**: Horizontal scaling architecture needs design doc update
