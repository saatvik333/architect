# Observability Guide

How to observe and debug the ARCHITECT system in a local development environment.

---

## Overview

The observability stack consists of:

- **Structured logging** via `structlog` (all services)
- **Distributed tracing** via OpenTelemetry + Jaeger
- **Prometheus metrics** with Grafana dashboards
- **Temporal UI** for workflow execution visibility
- **NATS monitoring endpoint** for message bus health
- **Docker tooling** (`docker stats`, `docker compose logs`) for infrastructure metrics

---

## Distributed Tracing (OpenTelemetry + Jaeger)

Services instrumented with `architect-observability` automatically export traces via OTLP gRPC.

### Accessing Jaeger

- **URL:** <http://localhost:16686>
- **OTLP endpoint:** `http://jaeger:4317` (from within Docker network)

### What's traced

- Every inbound HTTP request (FastAPI auto-instrumentation)
- Outbound HTTP calls (httpx auto-instrumentation)
- Span context is propagated across service boundaries via W3C Trace Context headers

### Instrumenting a new service

Add `architect-observability` to the service's `pyproject.toml`, then in `create_app()`:

```python
from architect_observability import init_observability

def create_app() -> FastAPI:
    app = FastAPI(...)
    app.include_router(router)
    init_observability(app, "service-name")
    return app
```

In the lifespan shutdown:

```python
from architect_observability import shutdown_observability

async def lifespan(app):
    yield
    shutdown_observability(app)
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317` to enable export (disabled when unset).

### Currently instrumented services

- `api-gateway` (port 8000)
- `world-state-ledger` (port 8001)

Other services can be instrumented by following the same pattern.

---

## Prometheus Metrics

Every instrumented service exposes a `/metrics` endpoint in Prometheus exposition format.

### Accessing Prometheus

- **URL:** <http://localhost:9090>
- **Scrape config:** `infra/prometheus/prometheus.yml`
- **Scrape interval:** 15 seconds

### Accessing Grafana

- **URL:** <http://localhost:3001>
- **Default credentials:** admin / admin (or `$GRAFANA_PASSWORD`)
- **Data source:** Add Prometheus at `http://prometheus:9090`

### Key metrics

- `http_requests_total` -- request count by method, path, status
- `http_request_duration_seconds` -- request latency histogram
- `http_requests_in_progress` -- current active requests

### Excluded paths

Health (`/health`) and metrics (`/metrics`) endpoints are excluded from instrumentation to avoid noise.

---

## Structured Logging

All services use the shared helper in `architect_common.logging`.

```python
from architect_common.logging import setup_logging, get_logger

setup_logging(log_level="DEBUG", json_output=False)
log = get_logger(service="my-service", component="worker")
log.info("task started", task_id=task_id)
```

**Key points:**

- `json_output=False` (default) -- human-readable console output via `ConsoleRenderer`. Set to `True` in production or when piping to a log aggregator to get JSON lines.
- Context fields added via `get_logger(**ctx)` are attached to every subsequent log entry from that logger.
- Thread-local context is merged automatically (`merge_contextvars`), so fields bound with `structlog.contextvars.bind_contextvars()` appear in all loggers within the same context.
- Logs are written to **stderr**.
- Supported levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

---

## Temporal Observability

The Temporal UI is available at <http://localhost:8080> (see `temporal-ui` in `infra/docker-compose.yml`).

Refer to the **Monitoring Temporal Workflows** section in [service-operations.md](service-operations.md) for detailed instructions on:

- Navigating workflow history and inspecting event payloads
- Checking task queue backlog and worker polling
- Identifying stuck workflows
- Resetting failed workflows

The Temporal server itself listens on port 7233 and depends on Postgres being healthy.

---

## NATS Monitoring

NATS exposes a monitoring HTTP endpoint on **port 8222** (launched with `-m 8222` in docker-compose).

```bash
# Server status
curl http://localhost:8222/varz

# Active connections
curl http://localhost:8222/connz

# JetStream account info (streams, consumers, storage)
curl http://localhost:8222/jsz

# Health check
curl http://localhost:8222/healthz
```

Use `/jsz?streams=true` for per-stream details including message counts and consumer lag.

---

## Infrastructure Metrics

See the **Infrastructure Operations** section in [service-operations.md](service-operations.md) for container log tailing and restart procedures.

Quick reference:

```bash
# Live CPU/memory/IO for all compose containers
docker stats $(docker compose -f infra/docker-compose.yml ps -q)

# Follow logs for a specific container
docker compose -f infra/docker-compose.yml logs -f nats
```

Resource limits are defined in `infra/docker-compose.yml` under each service's `deploy.resources.limits`. Production deployments use `infra/docker-compose.prod.yml` with increased limits.

---

## Port Reference

| Service | Port | Purpose |
| ------- | ---- | ------- |
| API Gateway | 8000 | Unified HTTP entry point |
| World State Ledger | 8001 | State management API |
| Task Graph Engine | 8003 | Task DAG + scheduler |
| Execution Sandbox | 8007 | Docker sandbox API |
| Evaluation Engine | 8008 | 7-layer eval pipeline |
| Coding Agent | 8009 | LLM code generation |
| Spec Engine | 8010 | NL-to-spec translation |
| Multi-Model Router | 8011 | Model tier routing |
| Codebase Comprehension | 8012 | AST indexing + embeddings |
| Agent Comm Bus | 8013 | NATS message bus API |
| Jaeger UI | 16686 | Distributed tracing |
| Jaeger OTLP | 4317 | Trace ingestion (gRPC) |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Metrics dashboards |
| Temporal UI | 8080 | Workflow visibility |
| NATS Monitoring | 8222 | Message bus health |
| PostgreSQL | 5432 | Primary database |
| Redis | 6379 | Cache + event streams |
| Temporal Server | 7233 | Workflow orchestration |
| NATS Client | 4222 | JetStream pub/sub |
