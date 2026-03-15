# Contributing to ARCHITECT

Thank you for your interest in contributing to ARCHITECT (Autonomous Recursive Coding Hierarchy for Integrated Task Engineering and Execution). This guide covers everything you need to get started.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Conventions](#project-conventions)
- [Adding a New Service](#adding-a-new-service)
- [Adding a New Evaluation Layer](#adding-a-new-evaluation-layer)
- [Running Tests](#running-tests)
- [Git Workflow](#git-workflow)

---

## Development Setup

### Prerequisites

- **Python 3.12+**
- **Docker** and **Docker Compose** (Docker Desktop or Docker Engine)
- **uv** -- will be installed automatically by `dev-setup.sh` if not present

### Quick Setup

```bash
# One-command setup (installs uv, syncs deps, starts infra, runs migrations)
./scripts/dev-setup.sh

# Or manually:
uv sync --all-packages --group dev
make infra-up
make migrate
```

The `dev-setup.sh` script handles the full workflow:

1. Installs `uv` if not already present
2. Syncs all workspace dependencies (`uv sync --all-packages --group dev`)
3. Copies `.env.example` to `.env` if no `.env` exists
4. Starts infrastructure services via Docker Compose (Postgres, Redis, Temporal, NATS)
5. Waits for Postgres to become healthy
6. Runs Alembic database migrations
7. Installs pre-commit hooks
8. Verifies that core libraries are importable

### Verifying Setup

```bash
make test        # The full test suite should pass
make lint        # Should show "All checks passed!"
make typecheck   # Should pass (mypy strict mode)
```

---

## Project Conventions

### Code Style

- **Python 3.12+** -- every module starts with `from __future__ import annotations`
- **Ruff** for linting and formatting (line-length 100, rules: `E`, `F`, `I`, `N`, `W`, `UP`, `B`, `A`, `SIM`, `RUF`)
- **Quote style:** double quotes, space indentation
- All domain models use **Pydantic v2** with `frozen=True` via `ArchitectBase` (immutable by default)
- Mutable state containers use `MutableBase`
- **Async by default** -- all I/O operations are async
- **structlog** for logging, **OpenTelemetry** for tracing

### Naming Conventions

- **Branded ID types:** `TaskId("task-abc123")`, `AgentId("agent-def456")`, `ProposalId(...)`, `EventId(...)`
- **ID generators:** `new_task_id()`, `new_agent_id()`, `new_proposal_id()`, `new_event_id()`
- **Services** use `snake_case` package names matching their directory `kebab-case` name (e.g., `services/world-state-ledger/` -> `world_state_ledger`)
- Each service has `api/` (FastAPI routes, dependencies) and `temporal/` (workflows, activities, worker) sub-packages

### Architecture Rules

- **Services NEVER import other services** -- only shared `libs/*` packages (`architect_common`, `architect_db`, `architect_events`, `architect_llm`, `architect_sandbox_client`, `architect_testing`)
- **All state mutations go through proposals** -- agent -> proposal -> validator -> commit
- **Events are append-only** -- never mutate event log entries
- **Sandboxed execution only** -- no code runs outside Docker containers
- **Communication between services** is exclusively via Temporal workflows and the NATS event bus

### Configuration

- Environment variables with `ARCHITECT_` prefix
- Nested config via `pydantic-settings`: `ARCHITECT_PG_HOST`, `ARCHITECT_REDIS_PORT`, etc.
- See `.env.example` for all available settings including Postgres, Redis, Temporal, sandbox, Claude API, and budget configuration

### Port Assignments

This is the authoritative port reference for local development. All other docs cross-reference this table.

**Application services:**

| Port | Service |
|------|---------|
| 3000 | Dashboard (dev) |
| 8000 | API Gateway |
| 8001 | World State Ledger |
| 8003 | Task Graph Engine |
| 8007 | Execution Sandbox |
| 8008 | Evaluation Engine |
| 8009 | Coding Agent |
| 8010 | Spec Engine |
| 8011 | Multi-Model Router |
| 8012 | Codebase Comprehension |
| 8013 | Agent Comm Bus |

**Infrastructure:**

| Port | Service |
|------|---------|
| 4222 | NATS (client) |
| 5432 | PostgreSQL |
| 6379 | Redis |
| 7233 | Temporal Server (gRPC) |
| 8080 | Temporal UI |
| 8222 | NATS Monitoring |

---

## Adding a New Service

Follow these steps to add a new microservice to the workspace:

1. **Create the service directory:**

   ```bash
   mkdir -p services/my-service/src/my_service/{api,temporal}
   mkdir -p services/my-service/tests
   ```

2. **Add `pyproject.toml`** -- copy from an existing service (e.g., `services/world-state-ledger/pyproject.toml`) and adjust the name, description, and dependencies.

3. **Create `src/my_service/__init__.py`:**

   ```python
   """My Service — brief description of what this service does."""
   ```

4. **Add to `known-first-party`** in the root `pyproject.toml` Ruff isort config:

   ```toml
   [tool.ruff.lint.isort]
   known-first-party = [
       # ... existing entries ...
       "my_service",
   ]
   ```

5. **Create standard sub-packages:**

   - `api/__init__.py`
   - `api/routes.py` -- FastAPI router with `/health` endpoint
   - `api/dependencies.py` -- FastAPI dependency injection
   - `temporal/__init__.py`
   - `temporal/workflows.py` -- Temporal workflow definitions
   - `temporal/activities.py` -- Temporal activity implementations
   - `temporal/worker.py` -- Temporal worker bootstrap

6. **Create `tests/` directory** with a `conftest.py` and initial test files.

7. **Sync the workspace:**

   ```bash
   uv sync --all-packages
   ```

8. **Add tests** and verify:

   ```bash
   uv run pytest services/my-service/tests/ -x -q
   ```

---

## Adding a New Evaluation Layer

The evaluation engine uses a layered pipeline where each layer runs an independent check (compilation, unit tests, linting, etc.) inside a sandbox session.

1. **Create the layer module:**

   ```
   services/evaluation-engine/src/evaluation_engine/layers/my_layer.py
   ```

2. **Inherit from `EvalLayerBase`:**

   ```python
   from __future__ import annotations

   from architect_common.enums import EvalLayer
   from evaluation_engine.layers.base import EvalLayerBase
   from evaluation_engine.models import LayerEvaluation


   class MyLayer(EvalLayerBase):
       @property
       def layer_name(self) -> EvalLayer:
           return EvalLayer.MY_LAYER

       async def evaluate(self, sandbox_session_id: str) -> LayerEvaluation:
           # Run checks inside the sandbox and return a LayerEvaluation
           ...
   ```

3. **Add the corresponding `EvalLayer` enum value** in `architect_common.enums` if it does not already exist.

4. **Register the layer in `Evaluator.__init__`** in `evaluation_engine/evaluator.py` by adding it to the default layer stack:

   ```python
   self._layers = [
       CompilationLayer(sandbox_client),
       UnitTestLayer(sandbox_client),
       MyLayer(sandbox_client),  # new layer
   ]
   ```

5. **Add tests** in `services/evaluation-engine/tests/` covering both success and failure paths.

---

## Running Tests

| Command | Description | Infrastructure Required |
|---|---|---|
| `make test` | Unit tests across all packages (fast) | No |
| `make test-integration` | Integration tests (`-m integration`) | Yes (Docker) |
| `make test-e2e` | Full lifecycle end-to-end tests (`-m e2e`) | Yes (Docker) |
| `make test-all` | All tests | Yes (Docker) |

### Running a single package

```bash
uv run pytest services/task-graph-engine/tests/ -x -q
```

### Running a single test file

```bash
uv run pytest services/world-state-ledger/tests/test_state_manager.py -x -q
```

### Test configuration

Tests use `pytest` with `--import-mode=importlib` and `asyncio_mode=auto`. Markers:

- `@pytest.mark.integration` -- requires running infrastructure (Postgres, Redis, etc.)
- `@pytest.mark.e2e` -- end-to-end tests
- `@pytest.mark.slow` -- tests that take >10 seconds

---

## Git Workflow

1. **Branch from `main`:**

   ```bash
   git checkout main
   git pull
   git checkout -b feat/my-feature
   ```

2. **Commit messages** follow conventional commit prefixes:

   - `feat:` -- new feature
   - `fix:` -- bug fix
   - `docs:` -- documentation update
   - `refactor:` -- code refactoring (no functional change)
   - `test:` -- adding or updating tests
   - `chore:` -- maintenance, dependency updates, CI changes

3. **Before pushing, run all checks:**

   ```bash
   make lint
   make typecheck
   make test
   ```

4. **Open a pull request** against `main`. A PR template is provided at `.github/pull_request_template.md` with checklists for testing, type checking, and linting.

5. **Keep PRs focused** -- one logical change per PR. If a change spans multiple services, explain the cross-service impact in the PR description.

## Changelog

ARCHITECT uses [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Every PR that changes behaviour, adds a feature, or fixes a bug **must** update `CHANGELOG.md`.

### Rules

- Add your entry under the `## [Unreleased]` section at the top of the file.
- Use one of these subsections:
  - `### Added` — new features or components
  - `### Changed` — changes to existing behaviour
  - `### Deprecated` — features that will be removed
  - `### Removed` — features removed in this release
  - `### Fixed` — bug fixes
  - `### Security` — security patches
- Write entries in past tense, from the user's perspective (e.g. "Added X" not "Adds X").
- The changelog check in CI will warn (not fail) if `CHANGELOG.md` is not touched — documentation-only PRs may skip this.

### Releasing a version

When cutting a release, move all `[Unreleased]` entries to a new versioned section:

```markdown
## [1.2.0] - 2026-04-01

### Added
- ...

[1.2.0]: https://github.com/saatvik333/architect/compare/v1.1.0...v1.2.0
```

Then push a git tag (`git tag v1.2.0 && git push origin v1.2.0`). The `release` GitHub Actions workflow will automatically create a GitHub Release with the extracted changelog notes.
