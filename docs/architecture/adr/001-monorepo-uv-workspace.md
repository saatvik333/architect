# ADR-001: uv Workspace Monorepo

## Status

Accepted

## Context

ARCHITECT is a multi-agent system composed of 14 services (world-state-ledger, task-graph-engine, execution-sandbox, evaluation-engine, coding-agent, spec-engine, multi-model-router, codebase-comprehension, agent-comm-bus, knowledge-memory, economic-governor, security-immune, deployment-pipeline, failure-taxonomy), 6 shared libraries (architect-common, architect-db, architect-events, architect-llm, architect-sandbox-client, architect-testing), and 2 applications (CLI, API gateway).

These components share a significant amount of code through the shared libraries. Pydantic domain models, enums (`StatusEnum`, `EvalVerdict`, `TaskType`, `ModelTier`, `EventType`, etc.), branded ID types (`TaskId`, `AgentId`, `ProposalId`, `EventId`), database ORM models, event schemas, LLM client utilities, and configuration classes are all used across multiple services. Keeping these in sync across independent repositories would create a major coordination burden.

Additionally, the team needs:

1. A single set of development tooling (ruff, mypy, pytest) with consistent configuration across all 22+ packages.
2. The ability to run `mypy --strict` across the entire codebase in one pass, catching cross-package type errors.
3. Atomic commits that span multiple services and libraries when contracts change (e.g., adding a field to `EventEnvelope` or renaming a shared enum variant).
4. A unified CI pipeline that validates everything together.
5. Fast, reproducible dependency resolution for Python 3.12+ with hundreds of transitive dependencies.

Alternatives considered:

- **Polyrepo (one repository per service/library)**: Would provide strong isolation between packages but at the cost of massive coordination overhead. Cross-cutting changes to shared libraries would require synchronized PRs across multiple repos. Dependency version drift between repos would be a constant source of integration failures.
- **pip + setuptools monorepo**: Possible but lacks workspace-native dependency resolution. The `pip install -e .` approach does not scale to 22+ packages. No single lockfile without additional tooling (pip-tools, pip-compile). Resolution speed is unacceptable for large dependency trees.
- **Poetry workspaces**: Poetry has experimental workspace support, but at the time of evaluation it lacked stable multi-package workspace management. Resolution speed is significantly slower than uv for large dependency trees, and the plugin ecosystem for workspace features was immature.

## Decision

Use **uv** (from Astral) as the package manager with its **workspace** feature to manage the entire ARCHITECT codebase as a monorepo.

The directory structure follows a three-tier layout:

```
/
  libs/           -- shared libraries (6 packages)
  services/       -- the 14 ARCHITECT service components
  apps/           -- CLI, API gateway
  pyproject.toml  -- root workspace configuration
  uv.lock         -- single lockfile for all packages
```

The root `pyproject.toml` defines workspace membership:

```toml
[tool.uv.workspace]
members = [
    "libs/*",
    "services/*",
    "apps/cli",
    "apps/api-gateway",
]
```

Each package has its own `pyproject.toml` with a `hatchling` build backend and declares its own dependencies in its local `pyproject.toml`. uv resolves workspace references automatically -- when `world-state-ledger` depends on `architect-common`, uv installs it as an editable workspace reference.

Shared development dependencies (pytest, pytest-asyncio, pytest-cov, pytest-xdist, ruff, mypy, pre-commit) are defined once in the root `[dependency-groups]` section and are available to all packages:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "pytest-xdist>=3.5",
    "ruff>=0.9",
    "mypy>=1.13",
    "pre-commit>=4.0",
]
```

Tooling configuration is centralized in the root `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["libs/*/src", "services/*/src", "apps/*/src"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM", "RUF"]

[tool.ruff.lint.isort]
known-first-party = [
    "architect_common", "architect_db", "architect_events",
    "architect_llm", "architect_sandbox_client", "architect_testing",
    "world_state_ledger", "task_graph_engine", "execution_sandbox",
    "evaluation_engine", "coding_agent", "architect_cli",
]

[tool.pytest.ini_options]
testpaths = ["libs", "services", "apps", "tests"]
addopts = "--import-mode=importlib -ra --strict-markers"
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

Commands:

- `make install` -- install all packages with `uv sync --all-packages`
- `make lint` -- ruff check + format check
- `make format` -- auto-format
- `make typecheck` -- mypy strict mode
- `make test` -- unit tests with pytest

## Consequences

### Positive

- **Single lockfile**: One `uv.lock` ensures all 22+ packages use identical dependency versions, eliminating "works on my machine" issues from version skew.
- **Workspace resolution**: Services can depend on `architect-common`, `architect-db`, etc. as editable workspace references. Changes to a library are immediately visible to all consumers without publishing or reinstalling.
- **Atomic refactors**: Renaming a shared type, updating an enum variant, or changing a Pydantic model schema can be done in a single commit that updates all consumers. This is critical for a system with deeply shared domain models.
- **Unified CI**: A single `make lint`, `make typecheck`, `make test` validates the entire codebase. No need to coordinate CI across multiple repositories.
- **Fast resolution**: uv's Rust-based resolver handles the full dependency tree in seconds (10-100x faster than pip or Poetry), keeping developer feedback loops short even with 22+ workspace members and hundreds of transitive dependencies.
- **Consistent tooling**: Every developer and CI run uses the same ruff rules (E, F, I, N, W, UP, B, A, SIM, RUF), mypy strictness level, pytest configuration, and Python version (3.12+).
- **Cross-package refactoring**: Tools like mypy can validate type correctness across package boundaries in a single run, catching errors that would be missed in a polyrepo setup.

### Negative

- **Deployment coupling**: Independent deployment of a single service requires extracting its dependency closure from the workspace. This can be mitigated with per-service Docker builds that install only the relevant packages.
- **Large lockfile**: A single lockfile for 22+ packages with overlapping dependencies can be large (the current `uv.lock` is ~256KB) and produce noisy diffs on updates. Reviewing lockfile changes requires tooling support.
- **Shared virtual environment**: All packages share the same `.venv` during development. A dependency conflict in one package affects the entire workspace. This is mitigated by uv's strict resolution, which flags conflicts early.
- **uv maturity**: While rapidly maturing, uv has less ecosystem history than pip or Poetry. Breaking changes in uv's workspace semantics could require migration effort, though this risk decreases as uv stabilizes.
- **Onboarding cost**: New contributors must install uv rather than using the pip that ships with Python. This is a one-time cost offset by significantly faster subsequent workflows.

### Neutral

- The monorepo does not mandate a shared deployment schedule. Services can be versioned and deployed independently as long as their shared library contracts are stable.
- The `hatchling` build backend is lightweight and well-supported, but any PEP 517-compliant backend could be used per-package if needed.
- The `libs/` packages are not published to PyPI; they exist only as workspace references. External publication would require additional configuration if needed in the future.
