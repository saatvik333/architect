# Phase 4: Best Practices & Standards

## Framework & Language Findings

### Medium (7)

1. **F-M1. Deprecated `asyncio.get_event_loop().run_in_executor` — 9 call sites**
   - Files: `docker_executor.py` (6), `file_manager.py` (3)
   - Fix: Replace with `asyncio.to_thread()`.

2. **F-M2. Mixed `logging`/`structlog` in 7 modules**
   - `architect-events` (publisher, subscriber, dlq), `architect-llm` (client), `spec-engine` (parser, stakeholder_simulator, scope_governor)
   - Fix: Replace `logging.getLogger(__name__)` with `get_logger(component=...)`.

3. **F-M3. Temporal activities create new `LLMClient` per call**
   - File: `coding_agent/temporal/activities.py`
   - Rate limiter state lost between calls, HTTP connection pool wasted.
   - Fix: Use dataclass-based activity pattern for DI.

4. **F-M4. String-based Temporal activity references in TaskOrchestrationWorkflow**
   - File: `task_graph_engine/temporal/workflows.py`
   - Bypasses type checking and IDE navigation.
   - Fix: Import activity functions and pass references directly.

5. **F-M5. Duplicated dot-path traversal in StateManager**
   - Same logic in `_apply_mutations` and `_validate_mutations`.
   - Fix: Extract `_set_at_path(data, path, value)` helper.

6. **F-M6. No React Error Boundaries in dashboard**
   - If `@xyflow/react` throws, the entire app crashes.
   - Fix: Add error boundary components around heavy/third-party renders.

7. **F-M7. `usePolling` missing request cancellation**
   - Stale fetch responses can overwrite fresh data; state updates on unmounted components.
   - Fix: Use `AbortController` in the polling hook.

### Low (9)

8. **F-L1.** Dead `TypeVar` alongside PEP 695 type parameter syntax in `base.py`.
9. **F-L2.** No `match/case` usage anywhere — missed readability opportunity.
10. **F-L3.** Inconsistent lifespan return types (`AsyncGenerator` vs `AsyncIterator`).
11. **F-L4.** `dir()` check for variable existence in workflow return value.
12. **F-L5.** Route DTOs inherit `BaseModel` instead of shared base config.
13. **F-L6.** Local import of `_resolve_pricing` in hot path (`client.py` line 96).
14. **F-L7.** Potentially unstable NATS API (`find_stream_info_by_subject`).
15. **F-L8.** TypeScript target could be ES2022+.
16. **F-L9.** Additional ruff lint rules (`TCH`, `PTH`, `PERF`) available.

### Positive Observations
- Consistent `from __future__ import annotations` across all 236 Python files
- No legacy `typing` generics — modern `X | None`, `dict[str, Any]` throughout
- No deprecated Pydantic v1 patterns — fully on v2 APIs
- Dependencies are modern and well-pinned (React 19, TS 5.6, Vite 8, FastAPI 0.115+)
- `structlog` is explicitly declared and configured (just not used everywhere)
- Dashboard uses Bun as specified in conventions

---

## CI/CD & DevOps Findings

### Critical (2)

1. **O-C1. No Deployment Strategy or CD Pipeline**
   - No deployment workflow, no K8s manifests, no Helm charts, no Terraform/Pulumi. Release builds container images but nothing deploys them.
   - Fix: Define deployment target, create manifests, implement CD with staging and manual prod approval.

2. **O-C2. No Environment Separation (dev/staging/prod)**
   - Single `.env.example` with dev config only. No staging or production configs, no environment-specific compose overrides.
   - Fix: Create environment-specific configurations and document promotion path.

### High (10)

3. **O-H1. Security Scans Silently Swallowed (`|| true`)**
   - Both `bandit` and `pip-audit` in CI append `|| true`, never failing the build.
   - Fix: Remove `|| true`, let medium+ findings block.

4. **O-H2. Container Images Use Unpinned `latest` Tags**
   - `temporalio/auto-setup:latest`, `temporalio/ui:latest`, `nats:latest` in docker-compose.
   - Fix: Pin to specific versions with sha256 digests.

5. **O-H3. Hardcoded Credentials Throughout Configs**
   - `architect_dev` password in docker-compose (Postgres and Temporal), `.env.example`, and CI.
   - Fix: Remove defaults for credentials, require explicit env vars.

6. **O-H4. Redis Has No Authentication**
   - Redis runs without `--requirepass`.
   - Fix: Add `--requirepass` and configure all clients.

7. **O-H5. Release Pushes Mutable `latest` Image Tag**
   - Every release overwrites `latest`, making deployments non-deterministic.
   - Fix: Stop pushing `latest`.

8. **O-H6. No Metrics, Alerting, or Distributed Tracing**
   - No Prometheus, Grafana, or OTel instrumentation. Only manual log inspection.
   - Fix: Add Prometheus metrics, OTel tracing (FastAPI + Temporal have official integrations).

9. **O-H7. No Rollback Procedure**
   - No documented or automated rollback mechanism.
   - Fix: Document manual rollback, implement automated rollback via image tag revert.

10. **O-H8. No Incident Response Procedures**
    - No on-call setup, escalation paths, or incident response runbook.
    - Fix: Create incident response runbook.

11. **O-H9. Docker Socket Exposure** (also covered in security findings)
    - Execution sandbox accesses host Docker socket.
    - Fix: Use DinD, rootless Docker, or Docker socket proxy.

12. **O-H10. No API Authentication** (also covered in security findings)
    - All endpoints unauthenticated.
    - Fix: Implement API key or OAuth2 auth on gateway.

### Medium (7)

13. **O-M1.** No coverage threshold enforcement — `--cov-fail-under` not set.
14. **O-M2.** Integration tests minimal (1 file, 2 tests) — no Temporal or NATS in CI.
15. **O-M3.** E2E tests never run in CI — skip when infra unavailable.
16. **O-M4.** Sandbox image not built in CI/release pipeline.
17. **O-M5.** Health check script has stale port mappings.
18. **O-M6.** Postgres 512MB memory limit too low for pgvector workloads.
19. **O-M7.** `Dockerfile.service` copies `uv:latest` — unpinned build dependency.

### Low (3)

20. **O-L1.** No container image scanning (Trivy/Grype) in CI.
21. **O-L2.** `dev-setup.sh` missing `pre-push` hook install.
22. **O-L3.** No multi-architecture container builds (arm64 support).
