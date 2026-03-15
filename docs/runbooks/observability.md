# Observability Guide

How to observe and debug the ARCHITECT system in a local development environment.

---

## Overview

The current observability stack consists of:

- **Structured logging** via `structlog` (all services)
- **Temporal UI** for workflow execution visibility
- **NATS monitoring endpoint** for message bus health
- **Docker tooling** (`docker stats`, `docker compose logs`) for infrastructure metrics

OpenTelemetry tracing is planned but not yet instrumented.

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

The Temporal UI is available at **http://localhost:8080** (see `temporal-ui` in `infra/docker-compose.yml`).

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

Resource limits are defined in `infra/docker-compose.yml` under each service's `deploy.resources.limits`.

---

## Future: OpenTelemetry

OTel tracing (via `opentelemetry-sdk` and the OTLP exporter) is planned but not yet wired in. The `structlog` processors are designed to coexist with OTel context propagation once it is added. This section will be expanded when instrumentation lands.
