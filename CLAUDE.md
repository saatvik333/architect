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
- Postgres 16, Redis 7, Temporal, NATS
- FastAPI, SQLAlchemy (async), Alembic
- Anthropic SDK (Claude API)
- Docker for sandboxing

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
- `make dev` — full local environment

## Documentation Maintenance
After completing any non-trivial change, automatically:
1. Update relevant `docs/` files (runbooks, API reference, architecture docs, ADRs) to reflect the change
2. Update `CLAUDE.md` if new conventions, commands, or components are added
3. Keep these updates in the same commit as the code change, or as a follow-up commit immediately after

## Phase 1 Components (active)

1. World State Ledger (Component 2)
2. Task Graph Engine (Component 3)
3. Execution Sandbox (Component 7)
4. Evaluation Engine (Component 8)
5. Coding Agent
