# Changelog

All notable changes to ARCHITECT will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Phase A Security Hardening
- **API key authentication** on all gateway endpoints (ADR-005 accepted) — `Authorization: Bearer <key>` with constant-time `hmac.compare_digest`, exempt health/docs paths (S-C2, CVSS 9.1 → resolved)
- **Redis authentication** — `--requirepass` in docker-compose, credentials redacted from logs (S-H3, CVSS 7.5 → resolved)
- **Prompt injection mitigation** — injection marker detection + `<user_input>` delimiter tags in LLM prompts + post-generation code security scan (S-H1, CVSS 8.2 → resolved)
- **Docker socket proxy** — Tecnativa docker-socket-proxy restricting API surface (S-H5, CVSS 7.8 → resolved)
- **Rate limiting** — sliding-window rate limiter middleware with 429 + Retry-After (S-M1 → resolved)
- **Request body size limits** — 1MB default, returns 413 on oversized requests (S-M7 → resolved)
- **Security headers** — CSP, HSTS (non-dev only), enhanced existing headers (S-M3 → resolved)
- **Credential auto-generation** — `scripts/dev-setup.sh` generates strong passwords for Postgres and Redis
- Hardcoded `architect_dev` credentials removed from docker-compose, config, and .env.example (O-H3, S-M2, S-M5 → resolved)

### Fixed
- Sandbox command filter replaced with allowlist + `shlex.split()` parsing (CVSS 9.8 → resolved)
- Path validation uses `Path.is_relative_to()` instead of string prefix matching (CVSS 8.6 → resolved)
- OCC guard with `SELECT ... FOR UPDATE` on state commits (CVSS 8.1 → resolved)
- CORS restricted to specific methods/headers, security headers middleware added
- Tar slip vulnerability in sandbox file read — member names validated
- Environment variable injection blocked for dangerous names (`LD_PRELOAD`, `PYTHONPATH`, etc.)
- Token usage double-counting bug in Coding Agent (`+=` → `=`)
- Hardcoded placeholder task/agent IDs in Temporal activities
- Thundering herd on state cache — probabilistic early expiration + 300s TTL
- Unbounded `_retry_counts` dict in EventSubscriber — bounded with pruning
- Module-level `app = create_app()` removed across all 9 services (factory pattern)
- Inconsistent logging (stdlib → structlog) across events, LLM, and spec-engine libs
- Redundant mutation traversal deduplicated via shared `_set_at_path()` helper
- Scheduler race condition prevented with atomic `schedule_and_claim()` under lock
- Connection pool sizing reduced to 5+5 per service (90 max across 9 services)
- Security scans (`bandit`, `pip-audit`) now block CI on findings
- Container images pinned to specific versions (Temporal, NATS, Redis, uv)
- Release workflow no longer pushes mutable `latest` tag
- Health check script corrected with actual service ports
- Port numbers fixed in service-operations runbook and phase-2-design doc
- Missing gateway routes added to API documentation
- Stale test/line counts replaced with non-stale phrasing

### Added
- `infra/seccomp/sandbox-profile.json` — whitelist-only seccomp profile blocking `ptrace`, `mount`, `unshare`, `CLONE_NEWUSER`, `keyctl`, `syslog`, `pivot_root`, `bpf`, `perf_event_open`, and kernel module operations
- 4 new DB repositories: `ProposalRepository`, `AgentSessionRepository`, `SandboxSessionRepository`, `EvaluationReportRepository`
- `BudgetExceededError` under the `BudgetError` hierarchy in `architect-common`
- `CostTracker.check_budget()` with configurable `max_budget_usd` and 75%/90% warning thresholds
- `LLMClient.max_tool_calls` guard to prevent recursive tool-use cost explosions
- CI: `security` job with Bandit SAST scan + CodeQL analysis on every push/PR
- CI: UV dependency caching (`enable-cache: true`) on all jobs — ~3-5 min savings per run
- CI: pytest-cov coverage reporting with Codecov upload
- Release: Docker image build and push to GHCR (`ghcr.io/saatvik333/architect/service`) on version tags
- Release: CHANGELOG entry validation before creating GitHub Release
- `bandit[toml]` and `pytest-cov` added to dev dependency group
- Event DLQ: `EventSubscriber` now tracks retry counts per message, moves to `{prefix}:dlq:{event_type}` after `max_retries` failures
- `EventSubscriber.claim_stale_messages()` using XAUTOCLAIM to reclaim stuck messages
- `EventSubscriber.get_dlq_messages()` for DLQ inspection
- `DeadLetterProcessor` class: `reprocess()`, `purge()`, `count()` for DLQ management
- Temporal `workflow.patched()` version markers on all 3 active workflows (task-graph, evaluation, coding-agent) for safe future migrations
- API Gateway: full implementation with typed Pydantic models, `ServiceClient` async proxy, CORS, `GatewayConfig` via pydantic-settings, exception handlers
- API Gateway routes: `POST /api/v1/tasks`, `GET /api/v1/tasks/{id}`, `GET /api/v1/tasks/{id}/logs`, `POST /api/v1/tasks/{id}/cancel`, `GET /api/v1/tasks/{id}/proposals`, `GET /api/v1/proposals/{id}`, `GET /api/v1/state`, `POST /api/v1/state/proposals`
- CLI: new `config show/set/reset` commands with `~/.config/architect/config.json` persistence
- CLI: new `watch` command with Rich Live display, progress bar, auto-exit on terminal state
- CLI: new `cancel` command with `--force` flag for cascading child cancellation
- CLI: new `proposals list/inspect` commands with tabular + JSON output
- CLI: new `state` command with dot-path filtering and syntax-highlighted JSON
- CLI `output.py`: `print_table()`, `print_json()`, `print_progress()` helpers
- **Specification Engine** (Component 1): `SpecParser` with LLM-driven NL→formal spec parsing, `SpecValidator`, clarification detection, Temporal workflow, FastAPI routes (`POST /api/v1/specs`, `GET /api/v1/specs/{id}`, `POST /api/v1/specs/{id}/clarify`)
- **Multi-Model Router** (Component 4): `ComplexityScorer` with weighted factors (task type, tokens, keywords), `Router` with tier thresholds and static overrides, `EscalationPolicy` (TIER_3→TIER_2→TIER_1→human), FastAPI routes (`POST /api/v1/route`, `GET /api/v1/route/stats`)
- **Codebase Comprehension** (Component 5): `ASTIndexer` (Python `ast` module), `CallGraphBuilder`, `ConventionExtractor`, `ContextAssembler` with keyword search, `IndexStore` (in-memory), FastAPI routes (`POST /api/v1/index`, `GET /api/v1/context`, `GET /api/v1/symbols`)
- **Agent Communication Bus** (Component 6): `MessageBus` wrapping NATS JetStream with publish/subscribe/request-reply, `DeadLetterHandler`, 8 typed `MessageType` variants, FastAPI routes (`GET /api/v1/bus/stats`, `POST /api/v1/bus/publish`)
- Evaluation Engine: 5 new layers — `IntegrationTestLayer`, `AdversarialLayer` (LLM-generated attack vectors), `SpecComplianceLayer`, `ArchitectureComplianceLayer`, `RegressionLayer` — completing all 7 layers from the architecture spec
- New error types: `SpecError`, `SpecAmbiguousError`, `SpecValidationError`, `CommBusError`, `MessageDeliveryError`, `MessageTimeoutError`, `RoutingError`, `NoAvailableTierError`
- New `EventType` variants: `SPEC_CREATED`, `SPEC_CLARIFICATION_NEEDED`, `SPEC_FINALIZED`, `ROUTING_DECISION`, `ROUTING_ESCALATION`, `MESSAGE_PUBLISHED`, `MESSAGE_DEAD_LETTERED`
- Test factories: `make_spec()`, `make_agent_message()`, `make_routing_decision()` in `architect-testing`
- Dashboard app (`apps/dashboard/`): Vite + React 18 + TypeScript + Tailwind dark-mode SPA with task list, task detail (timeline + logs), health grid, proposals view, 3s polling, `bun run build`
- API Gateway: proxy routes for all Phase 2 services (specs, routing, codebase indexing, message bus)
- `nats-py>=2.7` added to agent-comm-bus dependencies
- `architect-llm` added to evaluation-engine dependencies (for adversarial layer)
- React `ErrorBoundary` component wrapping entire dashboard
- `AbortController` in `usePolling` hook — cancels in-flight requests on unmount
- Lazy-loaded React routes via `React.lazy()` + `Suspense`
- `ScorerConfig` Pydantic model replacing magic numbers in ComplexityScorer
- `embed_chunks_async()` method wrapping blocking model.encode in `asyncio.to_thread()`
- Batched vector store inserts (500 per batch)
- LRU eviction in IndexStore (max 50 indices)
- Bounded `_run_store` in coding agent API (max 1000 entries, OrderedDict)
- `TaskDAG.update_task()` method for proper encapsulation
- Alembic migration 003: composite indexes on event_log and evaluation_reports FK
- Coverage threshold enforcement (`--cov-fail-under=60`) in CI and Makefile
- Pre-push hook installation in dev-setup.sh
- 5 Phase 1 service route test files (42 tests)
- Adversarial command filter bypass tests (57 parametrized cases)
- EventPublisher, EventSubscriber, and rate limiter test suites (54 tests)

### Changed
- `SecurityValidator` command blocklist: all patterns now case-insensitive; added full-path variants (`/bin/rm`, `/usr/bin/curl`, etc.); 12 new dangerous patterns (`mknod`, `eval`, `exec`, `LD_PRELOAD`, `/dev/shm`, `find -exec`, `base64 -d`, `/proc/self`, etc.)
- `SecurityValidator.validate_files()` now canonicalizes paths and rejects symlink escapes outside workspace root
- `resource_limits.py`: containers now drop all capabilities (`cap_drop=["ALL"]`) and add back only 5 minimal ones; `pids_limit=256` (fork bomb protection); `blkio_weight=100`; seccomp profile wired in
- `Dockerfile.sandbox`: workspace permissions `chmod 755` (not world-writable); added `HEALTHCHECK`; explicit `ENTRYPOINT ["python3"]`
- `docker-compose.yml`: fixed NATS healthcheck (was invalid command); added `deploy.resources.limits` to all 5 services; postgres password now sourced from `${POSTGRES_PASSWORD:-architect_dev}`
- `LLMClient`: calls `check_budget()` before every API call and before every retry to prevent over-spend
- Integration CI job now depends on `security` job completing
- Temporal DI pattern: module-level globals → `@dataclass` activity classes (WSL + coding agent)
- `compute_overall_verdict` → static method on `EvaluationReport`
- `EventLog.append()` accepts optional session parameter for transactional composition
- Task decomposer markdown fence handling uses regex instead of line-based stripping
- Docker image references in docs corrected to `pgvector/pgvector:pg16`

## [0.1.0] - 2026-03-13

### Added
- **World State Ledger** (Component 2): proposal-gated state mutations with dot-path addressing, Redis cache, and Postgres append-only event log
- **Task Graph Engine** (Component 3): DAG-based task decomposition into impl→test→review triplets, state-machine scheduler, Temporal workflow orchestration
- **Execution Sandbox** (Component 7): Docker-based code execution with resource limits, read-only rootfs, non-root user, command blocklist, and audit logging
- **Evaluation Engine** (Component 8): multi-layer evaluation pipeline — CompilationLayer (py_compile) and UnitTestLayer (pytest), with Temporal orchestration
- **Coding Agent** (Component 5): plan→generate→test→iterate loop, multi-model routing (Opus/Sonnet/Haiku tiers), fenced code block parser
- `libs/architect-common`: branded ID types (`TaskId`, `AgentId`, `ProposalId`, `EventId`), Pydantic v2 base models, full exception hierarchy, shared config via pydantic-settings
- `libs/architect-db`: async SQLAlchemy engine/session, 8 ORM models, generic `BaseRepository`, `TaskRepository`, `EventRepository`, Alembic migrations
- `libs/architect-events`: `EventEnvelope`, 11 event classes, `EventPublisher` (Redis Streams XADD), `EventSubscriber` (XREADGROUP consumer groups)
- `libs/architect-llm`: `LLMClient` (async Anthropic SDK), `CostTracker` with per-model pricing, `TokenBucketRateLimiter`, `PromptTemplate`
- `libs/architect-sandbox-client`: typed HTTP client for sandbox service
- `libs/architect-testing`: factory functions and mock implementations for testing
- `apps/cli`: Typer CLI with `submit`, `status`, `logs`, `health` commands and rich output
- Phase 2–5 service stubs (10 components): scaffolded with pyproject.toml and test directories
- uv workspace monorepo with `libs/`, `services/`, `apps/` layout
- Docker Compose infra: Postgres 16, Redis 7, Temporal (auto-setup), Temporal UI, NATS JetStream
- GitHub Actions CI: lint, typecheck, unit tests, integration tests (with Postgres + Redis services)
- Comprehensive documentation: README, ARCHITECTURE, CONTRIBUTING, runbooks, API reference, Phase 1 design, 4 ADRs

[Unreleased]: https://github.com/saatvik333/architect/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saatvik333/architect/releases/tag/v0.1.0
