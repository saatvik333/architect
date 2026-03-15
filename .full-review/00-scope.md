# Review Scope

## Target

Entire ARCHITECT codebase — a multi-agent autonomous coding system built as a uv workspace monorepo. Covers all production source code, tests, infrastructure, and tooling.

## Files

### Shared Libraries (`libs/`)
- `libs/architect-common/` — shared types, interfaces, errors, enums, logging, config
- `libs/architect-db/` — SQLAlchemy models (task, sandbox, proposal, ledger, event, evaluation, agent, spec), repository layer, migrations

### Services (`services/`)
- `services/world-state-ledger/` — Component 2: state tracking (Temporal workflows, FastAPI routes)
- `services/task-graph/` — Component 3: task dependency graph engine
- `services/coding-agent/` — Component 5: AI coding agent (Claude API integration)
- `services/execution-sandbox/` — Component 7: Docker-based code execution sandbox
- `services/evaluation-engine/` — Component 8: 7-layer evaluation pipeline
- `services/specification-engine/` — Component 1 (Phase 2): spec parsing and management
- `services/multi-model-router/` — Component 4 (Phase 2): LLM routing
- `services/codebase-comprehension/` — Component 5 (Phase 2): AST/embedding-based code understanding
- `services/agent-communication-bus/` — Component 6 (Phase 2): inter-agent messaging via NATS

### Apps (`apps/`)
- `apps/api-gateway/` — FastAPI unified API gateway
- `apps/cli/` — CLI tool (Typer-based)
- `apps/dashboard/` — React/TypeScript SPA (Bun tooling)

### Infrastructure & Tooling
- `infra/` — Docker Compose, Dockerfiles, Temporal configs
- `scripts/` — utility scripts (start/stop services, health checks)
- `tests/` — integration test suites
- `promptfoo/` — LLM prompt regression testing configs
- Root: `Makefile`, `pyproject.toml`, `.pre-commit-config.yaml`, `.github/` CI workflows

## Stats

- ~287 Python source files
- ~39 TypeScript/JavaScript files
- 14 service components (5 Phase 1 active, 4 Phase 2 active, 5 Phase 3-5 stubs)

## Flags

- Security Focus: no
- Performance Critical: no
- Strict Mode: no
- Framework: FastAPI + SQLAlchemy (async) + React/TypeScript

## Review Phases

1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
