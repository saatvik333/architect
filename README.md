# ARCHITECT

**Autonomous Recursive Coding Hierarchy for Integrated Task Engineering and Execution**

> One system. One loop. Every engineer replaced.

---

## What is ARCHITECT?

ARCHITECT is an autonomous multi-agent system that implements the full software engineering loop:

**specify --> build --> test --> deploy --> observe --> repair --> learn**

It decomposes high-level project specifications into a directed acyclic graph of tasks, assigns them to LLM-powered agents, executes code in isolated Docker sandboxes, evaluates results through a multi-layer pipeline, and records every state change in a proposal-gated ledger.

The system is composed of **14 components** across **5 build phases**. Phase 1 (Foundation) and Phase 2 (Multi-Agent & Evaluation) are fully implemented. Phases 3--5 are stubbed and ready for incremental build-out.

---

## Architecture Overview

```
                         +------------------+
                         |   CLI / API      |
                         |   Gateway        |
                         +--------+---------+
                                  |
                                  v
                    +-------------+-------------+
                    |    Task Graph Engine       |
                    |  (DAG decomposition +      |
                    |   priority scheduler)      |
                    +---+--------+----------+---+
                        |        |          |
           +------------+   +---+---+  +---+----------+
           v                v       v  v              v
   +--------------+  +----------+  +----------------+
   | Coding Agent |  | Spec     |  | Multi-Model    |
   | (plan/gen/   |  | Engine   |  | Router         |
   |  fix loop)   |  | [P2]     |  | [P2]           |
   +------+-------+  +----------+  +----------------+
          |
          v
   +--------------+        +-----------------+
   |  Execution   |------->|  Evaluation     |
   |  Sandbox     |        |  Engine         |
   |  (Docker)    |        |  (7 layers)     |
   +--------------+        +--------+--------+
                                    |
                      +-------------+-------------+
                      |                           |
                      v                           v
             +----------------+          +----------------+
             | PASS: commit   |          | FAIL: retry or |
             | to ledger      |          | escalate       |
             +-------+--------+          +-------+--------+
                     |                           |
                     v                           v
          +-------------------+       +-------------------+
          | World State       |       | Failure Taxonomy  |
          | Ledger            |       | [P4]              |
          | (single source    |       +-------------------+
          |  of truth)        |
          +---------+---------+
                    |
     +--------------+--------------+
     |              |              |
     v              v              v
+-----------+ +-----------+ +-----------+
| Knowledge | | Economic  | | Security  |
| Memory    | | Governor  | | Immune    |
| [P3]      | | [P3]      | | [P3]      |
+-----------+ +-----------+ +-----------+
```

### All 14 Components

| #   | Component                  | Phase | Description                                                                |
| --- | -------------------------- | ----- | -------------------------------------------------------------------------- |
| 1   | **Spec Engine**            | P2    | NL-to-formal-spec parsing via Claude LLM, clarification detection          |
| 2   | **World State Ledger**     | P1    | Single source of truth -- proposal-gated, versioned world state            |
| 3   | **Task Graph Engine**      | P1    | DAG-based task decomposition, dependency tracking, priority scheduling     |
| 4   | **Multi-Model Router**     | P2    | Complexity scoring + tier routing with escalation policy                    |
| 5   | **Codebase Comprehension** | P2    | Python AST indexing, call graph, convention extraction, context assembly    |
| 6   | **Agent Comm Bus**         | P2    | NATS JetStream pub/sub/request-reply with dead letter handling             |
| 7   | **Execution Sandbox**      | P1    | Docker-isolated code execution with resource limits and security scanning  |
| 8   | **Evaluation Engine**      | P1+P2 | 7-layer evaluation: compilation, unit/integration tests, adversarial, spec compliance, architecture, regression |
| 9   | **Knowledge Memory**       | P3    | 5-layer memory hierarchy for patterns, failures, and solutions             |
| 10  | **Economic Governor**      | P3    | Token budget enforcement and cost optimization                             |
| 11  | **Security Immune**        | P3    | Automated security scanning and vulnerability detection                    |
| 12  | **Deployment Pipeline**    | P4    | Canary deploys, health checks, and automatic rollback                      |
| 13  | **Failure Taxonomy**       | P4    | Structured failure classification and learning                             |
| 14  | **Human Interface**        | P5    | Dashboard, escalation UI, and human-in-the-loop controls                   |
| --  | **Coding Agent**           | P1    | LLM-powered code generation with plan/generate/test/fix loop               |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (for sandboxing and infrastructure)
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Clone and install
git clone <repo>
cd architect
make install

# Start infrastructure (Postgres, Redis, Temporal, NATS)
make infra-up

# Run database migrations
make migrate

# Run tests
make test

# Start a service (example)
uv run python -m world_state_ledger.service
```

---

## Project Structure

```
architect/
├── libs/                          # Shared libraries (no inter-service deps)
│   ├── architect-common/          # Types, enums, errors, config, interfaces
│   ├── architect-db/              # SQLAlchemy ORM models, repositories, migrations
│   ├── architect-events/          # Event schemas, Redis Streams pub/sub
│   ├── architect-llm/             # Claude API client, cost tracker, rate limiter
│   ├── architect-sandbox-client/  # Sandbox execution client
│   └── architect-testing/         # Test factories and mocks
├── services/                      # The 14 ARCHITECT components
│   ├── world-state-ledger/        # [P1] Single source of truth
│   ├── task-graph-engine/         # [P1] DAG task decomposition + scheduler
│   ├── execution-sandbox/         # [P1] Docker-isolated code execution
│   ├── evaluation-engine/         # [P1] Multi-layer code evaluation
│   ├── coding-agent/              # [P1] LLM-powered code generation
│   ├── spec-engine/               # [P2] NL→formal spec via LLM
│   ├── multi-model-router/        # [P2] Complexity scoring + tier routing
│   ├── codebase-comprehension/    # [P2] AST indexing + context assembly
│   ├── agent-comm-bus/            # [P2] NATS JetStream messaging
│   ├── knowledge-memory/          # [P3] 5-layer memory hierarchy
│   ├── economic-governor/         # [P3] Budget enforcement
│   ├── security-immune/           # [P3] Security scanning
│   ├── deployment-pipeline/       # [P4] Canary deploys + rollback
│   ├── failure-taxonomy/          # [P4] Structured learning
│   └── human-interface/           # [P5] Dashboard + escalation
├── apps/                          # User-facing applications
│   ├── cli/                       # CLI: architect submit/status/logs/health
│   ├── api-gateway/               # Unified API gateway
│   └── dashboard/                 # React + TypeScript + Tailwind dark-mode SPA
├── infra/                         # Docker Compose, Dockerfiles, SQL init scripts
├── tests/                         # Integration and E2E tests
│   ├── integration/               # Tests requiring infrastructure
│   └── e2e/                       # Full task lifecycle tests
├── scripts/                       # Dev setup and health check scripts
├── .github/                       # CI/CD workflows
├── pyproject.toml                 # Workspace root: uv workspace config
└── Makefile                       # Development commands
```

---

## Tech Stack

| Category               | Technology                   | Purpose                                              |
| ---------------------- | ---------------------------- | ---------------------------------------------------- |
| Language               | Python 3.12+                 | Runtime                                              |
| Package management     | uv + hatchling               | Monorepo workspace, fast installs, builds            |
| State persistence      | PostgreSQL 16                | World state ledger, event log, task storage          |
| Hot cache / pub-sub    | Redis 7                      | State cache, Redis Streams event bus                 |
| Workflow orchestration | Temporal                     | Durable execution, automatic retries, crash recovery |
| Inter-agent messaging  | NATS JetStream               | Typed pub/sub/request-reply between agents           |
| Dashboard              | React 18 + Vite + Tailwind   | Dark-mode SPA for task monitoring and health         |
| JS tooling             | Bun                          | Package management and builds for dashboard          |
| HTTP APIs              | FastAPI                      | Service REST endpoints                               |
| ORM                    | SQLAlchemy (async) + Alembic | Database models, migrations                          |
| LLM integration        | Anthropic SDK (Claude)       | Code generation, task decomposition, review          |
| Sandbox isolation      | Docker                       | Secure, resource-limited code execution              |
| Task DAG               | NetworkX                     | Directed acyclic graph management                    |
| Domain models          | Pydantic v2 (frozen)         | Immutable models, validation, serialization          |
| Logging                | structlog                    | Structured, JSON-compatible logging                  |
| Linting / formatting   | Ruff                         | Fast Python linting and auto-formatting              |
| Type checking          | mypy (strict)                | Static type analysis                                 |
| Testing                | pytest                       | Unit, integration, and E2E tests                     |

---

## Development Commands

| Command                 | Description                                                               |
| ----------------------- | ------------------------------------------------------------------------- |
| `make install`          | Install all workspace packages and dev dependencies                       |
| `make lint`             | Run ruff check + format check                                             |
| `make format`           | Auto-format all code with ruff                                            |
| `make typecheck`        | Run mypy in strict mode across libs, services, and apps                   |
| `make test`             | Run unit tests (libs + services + apps)                                   |
| `make test-integration` | Run integration tests (requires running infrastructure)                   |
| `make test-e2e`         | Run end-to-end tests (full task lifecycle)                                |
| `make test-all`         | Run all tests (unit + integration + E2E)                                  |
| `make infra-up`         | Start infrastructure via Docker Compose (Postgres, Redis, Temporal, NATS) |
| `make infra-down`       | Stop infrastructure containers                                            |
| `make migrate`          | Run Alembic database migrations                                           |
| `make dev`              | Start infrastructure + run migrations (full local env)                    |
| `make clean`            | Remove `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`       |

---

## Phase Roadmap

| Phase  | Name                       | Components                                                                                | Status          |
| ------ | -------------------------- | ----------------------------------------------------------------------------------------- | --------------- |
| **P1** | Foundation                 | World State Ledger, Task Graph Engine, Execution Sandbox, Evaluation Engine, Coding Agent | **IMPLEMENTED** |
| **P2** | Multi-Agent and Evaluation | Spec Engine, Multi-Model Router, Codebase Comprehension, Agent Comm Bus, Dashboard        | **IMPLEMENTED** |
| **P3** | Intelligence and Autonomy  | Knowledge Memory, Economic Governor, Security Immune                                      | STUB            |
| **P4** | Production Hardening       | Deployment Pipeline, Failure Taxonomy                                                     | STUB            |
| **P5** | Scale and Domain Expansion | Human Interface                                                                           | STUB            |

---

## Testing

- **502 tests** passing across all packages
- Unit tests colocated in each library and service package
- Integration tests in `tests/integration/` -- require running infrastructure (`make infra-up`)
- E2E tests in `tests/e2e/` -- test the full task submission-to-completion lifecycle

```bash
# Run unit tests only
make test

# Run integration tests (start infra first)
make infra-up
make test-integration

# Run E2E tests
make test-e2e

# Run everything
make test-all
```

Dashboard build:

```bash
cd apps/dashboard && bun install && bun run build
```

Test configuration: pytest with `--import-mode=importlib`, `asyncio_mode=auto`, strict markers for `integration`, `e2e`, and `slow`.

---

## License

TODO
