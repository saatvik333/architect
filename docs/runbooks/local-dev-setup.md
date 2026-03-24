# Local Development Setup

Step-by-step guide to set up the ARCHITECT development environment on your local machine.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Python | 3.12+ | Check with `python3 --version` |
| Docker | 20.10+ | Docker Desktop or Docker Engine + Docker Compose |
| Bun | 1.0+ | For dashboard app (`bun --version`) |
| RAM | 8 GB+ | Postgres, Redis, Temporal, and NATS run concurrently |

### Required Ports

The following ports must be free before starting infrastructure:

| Port | Service |
|---|---|
| 5432 | PostgreSQL 16 |
| 6379 | Redis 7 |
| 7233 | Temporal Server |
| 8080 | Temporal UI |
| 4222 | NATS (client connections) |
| 8222 | NATS Monitoring |
| 4317 | Jaeger OTLP (tracing) |
| 16686 | Jaeger UI |
| 9090 | Prometheus |
| 3001 | Grafana |

Check for port conflicts:

```bash
# Linux
ss -tlnp | grep -E '(5432|6379|7233|8080|4222|8222|4317|16686|9090|3001)'

# macOS
lsof -iTCP -sTCP:LISTEN -P | grep -E '(5432|6379|7233|8080|4222|8222|4317|16686|9090|3001)'
```

---

## Step 1: Install uv

[uv](https://docs.astral.sh/uv/) is the package manager used by ARCHITECT.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, ensure `uv` is on your `PATH`:

```bash
uv --version
```

---

## Step 2: Clone and Install

```bash
git clone <repo-url>
cd architect
uv sync --all-packages --group dev
```

This installs all workspace members (`libs/*`, `services/*`, `apps/*`) and dev dependencies (pytest, ruff, mypy, pre-commit) into a single virtual environment at `.venv/`.

Alternatively, use the one-command setup script which handles everything from Step 1 onward:

```bash
./scripts/dev-setup.sh
```

---

## Step 3: Environment Configuration

The easiest approach is to use the setup script, which auto-generates secure credentials:

```bash
./scripts/dev-setup.sh
```

This creates `.env` from `.env.example` and generates random passwords for Postgres and Redis via `openssl rand -hex 16`.

**Manual setup** (if you prefer):

```bash
cp .env.example .env
# Then edit .env and set REQUIRED values:
#   POSTGRES_PASSWORD=<strong-password>
#   ARCHITECT_PG_PASSWORD=<same-as-above>
#   REDIS_PASSWORD=<strong-password>
#   ARCHITECT_REDIS_PASSWORD=<same-as-above>
```

Key settings:

- `POSTGRES_PASSWORD` / `ARCHITECT_PG_PASSWORD` -- **Required.** Must match. Used by docker-compose and Python services
- `REDIS_PASSWORD` / `ARCHITECT_REDIS_PASSWORD` -- **Required.** Must match. Redis authentication
- `ARCHITECT_GATEWAY_API_KEYS_RAW` -- Comma-separated API keys for gateway auth (optional for local dev)
- `ARCHITECT_GATEWAY_AUTH_ENABLED` -- Set to `false` to skip auth locally (default: `true`)
- `ARCHITECT_CLAUDE_API_KEY` -- Set to your Anthropic API key for coding agent features
- `OTEL_EXPORTER_OTLP_ENDPOINT` -- Set to `http://jaeger:4317` to enable tracing (optional)

---

## Step 4: Start Infrastructure

```bash
make infra-up
```

This runs `docker compose -f infra/docker-compose.yml up -d`, starting:

- **PostgreSQL 16** -- primary database (with health check)
- **Redis 7** -- caching and event streams (requires password, append-only)
- **Temporal** -- workflow orchestration (auto-setup image, depends on Postgres)
- **Temporal UI** -- web dashboard for workflow visibility
- **NATS** -- event bus with JetStream enabled (with health check)
- **Jaeger** -- distributed tracing (OTLP on 4317, UI on 16686)
- **Prometheus** -- metrics collection (scrapes all services on 9090)
- **Grafana** -- metrics dashboards (UI on 3001)
- **Docker Socket Proxy** -- restricted Docker API access for sandbox security

Wait for all services to become healthy:

```bash
docker compose -f infra/docker-compose.yml ps
```

All services should show status `healthy` or `running`. Postgres typically takes 5-10 seconds to initialize.

---

## Step 5: Run Migrations

```bash
make migrate
```

This runs Alembic migrations against the local Postgres instance, creating all required tables (tasks, event_log, world_state_ledger, etc.).

---

## Step 6: Verify

```bash
make test          # The full test suite should pass
make lint          # Should report no issues
make typecheck     # mypy strict mode should pass
```

If all three commands succeed, your environment is fully operational.

---

## Step 7: Run Services

Each ARCHITECT service runs as an independent process. Start them in separate terminal sessions:

```bash
# Phase 1 services
uv run python -m world_state_ledger.service       # Port 8001
uv run python -m task_graph_engine.service         # Port 8003
uv run python -m execution_sandbox.service         # Port 8007
uv run python -m evaluation_engine.service         # Port 8008
uv run python -m coding_agent.service              # Port 8009

# Phase 2 services
uv run python -m spec_engine.service               # Port 8010
uv run python -m multi_model_router.service        # Port 8011
uv run python -m codebase_comprehension.service    # Port 8012
uv run python -m agent_comm_bus.service            # Port 8013

# API Gateway
uv run python -m api_gateway.service               # Port 8000
```

### Dashboard (React SPA)

```bash
cd apps/dashboard
bun install
bun run dev    # Dev server on http://localhost:3000
```

To build for production:

```bash
bun run build  # Output in apps/dashboard/dist/
```

---

## Accessing UIs

| UI | URL | Description |
| --- | --- | --- |
| Temporal UI | <http://localhost:8080> | View workflows, task history, and failures |
| Jaeger UI | <http://localhost:16686> | Distributed tracing across services |
| Prometheus | <http://localhost:9090> | Metrics queries and alerting |
| Grafana | <http://localhost:3001> | Metrics dashboards (admin/admin) |
| NATS Monitoring | <http://localhost:8222> | NATS server stats, connections, JetStream info |

---

## Troubleshooting

### Port Conflicts

If ports are already in use:

```bash
make infra-down
# Identify and stop the conflicting process, then:
make infra-up
```

### Database Issues

Check Postgres logs:

```bash
docker compose -f infra/docker-compose.yml logs postgres
```

Common causes:
- Port 5432 in use by a system Postgres installation
- Corrupted volume data (see "Reset Everything" below)

### Temporal Not Starting

Temporal depends on Postgres being healthy. If Temporal fails to start:

```bash
docker compose -f infra/docker-compose.yml logs temporal
```

Ensure Postgres is fully initialized before Temporal attempts to connect.

### Import Errors After Pulling New Changes

Re-sync dependencies:

```bash
uv sync --all-packages --group dev
```

### Reset Everything

Nuclear option -- removes all containers, volumes, and cached data:

```bash
make infra-down
docker volume prune -f
make infra-up
make migrate
```

### Clean Build Artifacts

```bash
make clean
```

This removes `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, and `*.egg-info` directories.

---

## Stopping

```bash
make infra-down
```

This stops and removes all Docker Compose containers. Persistent data (Postgres, Redis) is retained in Docker volumes. Use `docker volume prune` to remove volumes if a full reset is needed.
