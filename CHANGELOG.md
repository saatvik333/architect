# Changelog

All notable changes to ARCHITECT will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet.

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
