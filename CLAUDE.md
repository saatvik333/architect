# ARCHITECT Project

## Overview
Autonomous Recursive Coding Hierarchy for Integrated Task Engineering and Execution.
A multi-agent system that replaces the software engineering loop: specify → build → test → deploy → observe → repair → learn.

## Project Structure
- **uv workspace monorepo** with `libs/`, `services/`, `apps/` top-level dirs
- `libs/*` — shared libraries (no inter-service dependencies)
- `services/*` — the 14 ARCHITECT components (communicate via Temporal + event bus only)
- `apps/*` — CLI, dashboard, API gateway

## Tech Stack
- Python 3.12+, uv, hatchling
- Postgres 16 (with pgvector extension), Redis 7, Temporal, NATS
- FastAPI, SQLAlchemy (async), Alembic
- Anthropic SDK (Claude API)
- Docker for sandboxing
- Bun (for dashboard app JS/TS tooling — never use npm)
- tree-sitter (multi-language AST parsing in Codebase Comprehension)
- sentence-transformers (code embedding generation)
- PromptFoo (LLM prompt regression testing)

## Conventions
- All domain models use Pydantic v2 with `frozen=True` (immutable by default)
- Branded ID types: `TaskId`, `AgentId`, `ProposalId`, `EventId` (NewType with prefixes)
- Services never import other services — only shared libs
- State mutations go through the proposal pipeline (agent → proposal → validator → commit)
- Every service has `temporal/` (workflows, activities, worker) and `api/` (FastAPI routes) sub-packages
- Use `structlog` for logging, OpenTelemetry for tracing
- Tests: pytest with `--import-mode=importlib`, `asyncio_mode=auto`

## Commands
- `make install` — install all packages
- `make lint` — ruff check + format check
- `make format` — auto-format
- `make typecheck` — mypy strict mode
- `make test` — unit tests
- `make test-integration` — integration tests (requires infra)
- `make infra-up` / `make infra-down` — docker compose
- `make dev` — full local environment (infra-up + migrate)
- `make migrate` — run Alembic database migrations
- `make run-all` — start everything (infra + services + gateway + dashboard)
- `make stop-all` — stop all services and infrastructure
- `make promptfoo-test` — run LLM prompt regression tests (requires ANTHROPIC_API_KEY)
- `make promptfoo-view` — open PromptFoo test results viewer

## Documentation Maintenance
After completing any non-trivial change, automatically:
1. Update relevant `docs/` files (runbooks, API reference, architecture docs, ADRs) to reflect the change
2. Update `CLAUDE.md` if new conventions, commands, or components are added
3. Keep these updates in the same commit as the code change, or as a follow-up commit immediately after

## Phase 1 Components (active)

1. World State Ledger (Component 2)
2. Task Graph Engine (Component 3)
3. Execution Sandbox (Component 7)
4. Evaluation Engine (Component 8) — all 7 layers
5. Coding Agent (Component 5)

## Phase 2 Components (active)

1. Specification Engine (Component 1) — port 8010
2. Multi-Model Router (Component 4) — port 8011
3. Codebase Comprehension (Component 5) — port 8012
4. Agent Communication Bus (Component 6) — port 8013
5. Dashboard (React/TypeScript SPA) — `apps/dashboard/`, dev port 3000

## Phase 3–5 Components (stubs only)

- Knowledge & Memory (Component 9)
- Economic Governor (Component 10)
- Security Immune System (Component 11)
- Deployment Pipeline (Component 12)
- Failure Taxonomy (Component 13)
- Human Interface (Component 14)
