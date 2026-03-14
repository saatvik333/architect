# Service Operations Runbook

Operational procedures for monitoring, debugging, and maintaining ARCHITECT services.

---

## Service Health Checks

### Check All Services

```bash
python scripts/check-health.py
```

The health check script probes all 14 ARCHITECT services at their `/health` endpoints and reports status. Use `--timeout` to adjust the per-service timeout and `--wait` to poll until all services become healthy:

```bash
python scripts/check-health.py --timeout 10 --wait 60
```

### Individual Service Health

```bash
# Phase 1 services
curl http://localhost:8001/health  # Task Graph Engine
curl http://localhost:8002/health  # World State Ledger
curl http://localhost:8003/health  # Execution Sandbox
curl http://localhost:8004/health  # Evaluation Engine
curl http://localhost:8005/health  # Coding Agent

# Phase 2 services
curl http://localhost:8010/health  # Spec Engine
curl http://localhost:8011/health  # Multi-Model Router
curl http://localhost:8012/health  # Codebase Comprehension
curl http://localhost:8013/health  # Agent Comm Bus

# Gateway (aggregates all above)
curl http://localhost:8000/health  # API Gateway
```

A healthy service returns HTTP 200 with a JSON body.

---

## Monitoring Temporal Workflows

### Temporal UI

Open **http://localhost:8080** in your browser.

- **Namespace:** `architect`
- **Task Queue:** `architect-tasks`

### Key Views

| View | What to Look For |
|---|---|
| Workflows | Running, completed, and failed workflow executions |
| Workflow Detail | Full event history, input/output payloads, and retry state |
| Task Queues | Worker polling activity and backlog size |
| Schedules | Scheduled workflow triggers (if configured) |

### Identifying Stuck Workflows

1. Open Temporal UI -> Workflows
2. Filter by status: **Running**
3. Sort by start time (oldest first)
4. Workflows running significantly longer than expected may be stuck waiting for an activity or signal
5. Check the event history for the last recorded event and its timestamp

### Retrying Failed Workflows

From Temporal UI, navigate to the failed workflow and use the **Reset** action to replay from a specific point in the event history.

---

## Database Operations

### Connecting to Postgres

```bash
docker exec -it $(docker compose -f infra/docker-compose.yml ps -q postgres) psql -U architect
```

### Useful Queries

**List all tables:**

```sql
\dt
```

**Check recent tasks:**

```sql
SELECT id, type, status, verdict
FROM tasks
ORDER BY created_at DESC
LIMIT 10;
```

**Inspect the event log:**

```sql
SELECT id, type, task_id, timestamp
FROM event_log
ORDER BY timestamp DESC
LIMIT 20;
```

**Check world state ledger versions:**

```sql
SELECT version, updated_at
FROM world_state_ledger
ORDER BY version DESC
LIMIT 5;
```

**Find events for a specific task:**

```sql
SELECT id, type, timestamp, payload
FROM event_log
WHERE task_id = 'task-abc123'
ORDER BY timestamp ASC;
```

**Count events by type:**

```sql
SELECT type, COUNT(*) as count
FROM event_log
GROUP BY type
ORDER BY count DESC;
```

---

## Redis Operations

### Connecting to Redis

```bash
docker exec -it $(docker compose -f infra/docker-compose.yml ps -q redis) redis-cli
```

### Useful Commands

**Check cached world state snapshot:**

```
GET architect:ledger:snapshot:latest
```

**View active agents:**

```
SMEMBERS architect:agent:active
```

**Check remaining budget:**

```
GET architect:budget:remaining
```

**List all ARCHITECT keys:**

```
KEYS architect:*
```

**Check Redis memory usage:**

```
INFO memory
```

**Monitor commands in real time:**

```
MONITOR
```

(Press Ctrl+C to stop monitoring.)

---

## Infrastructure Operations

### Viewing Container Logs

```bash
# All infrastructure logs
docker compose -f infra/docker-compose.yml logs -f

# Specific service
docker compose -f infra/docker-compose.yml logs -f postgres
docker compose -f infra/docker-compose.yml logs -f redis
docker compose -f infra/docker-compose.yml logs -f temporal
docker compose -f infra/docker-compose.yml logs -f nats
```

### Restarting a Single Infrastructure Service

```bash
docker compose -f infra/docker-compose.yml restart redis
```

### Checking Container Resource Usage

```bash
docker stats $(docker compose -f infra/docker-compose.yml ps -q)
```

---

## Common Issues and Fixes

| Symptom | Likely Cause | Fix |
|---|---|---|
| Service returns HTTP 503 | Postgres or Redis connection lost | Check infrastructure: `docker compose -f infra/docker-compose.yml ps`. Restart unhealthy containers. |
| `ConnectionRefusedError` on port 5432 | Postgres not running or port conflict | `make infra-down && make infra-up`. Check for system Postgres on the same port. |
| `ConnectionRefusedError` on port 7233 | Temporal not ready | Temporal depends on Postgres. Ensure Postgres is healthy first: `docker compose -f infra/docker-compose.yml logs temporal`. |
| Temporal workflow stuck in "Running" | Activity timeout or worker crash | Check Temporal UI for the last event. Restart the service worker process. |
| `NATS: connection refused` on port 4222 | NATS not running | `docker compose -f infra/docker-compose.yml restart nats` |
| `alembic.util.exc.CommandError` during migration | Database schema out of sync | Run `make migrate`. If that fails, check `docker compose -f infra/docker-compose.yml logs postgres` for errors. As a last resort, drop and recreate: `docker compose -f infra/docker-compose.yml down -v && make infra-up && make migrate`. |
| Tests fail with `ModuleNotFoundError` | Dependencies out of sync after pulling new changes | Run `uv sync --all-packages --group dev` |
| Ruff reports formatting errors | Code not formatted | Run `make format` then re-run `make lint` |
| mypy reports import errors for `temporalio`, `docker`, or `nats` | Expected behavior -- these are configured as `ignore_missing_imports` | Verify the error is only for third-party stubs. If mypy fails on project code, fix the type annotations. |
| Redis `OOM` errors | Redis memory limit exceeded | Check memory with `redis-cli INFO memory`. Flush stale keys or increase Docker memory allocation. |
| Service health check passes but API returns 500 | Application-level error | Check the service logs (`uv run python -m <service>.service` terminal output). Look for structlog error entries with traceback details. |

---

## Runbook: Full Environment Reset

When the local environment is in an unrecoverable state:

```bash
# 1. Stop all services (Ctrl+C in each service terminal)

# 2. Tear down infrastructure and remove volumes
make infra-down
docker volume prune -f

# 3. Clean build artifacts
make clean

# 4. Re-sync dependencies
uv sync --all-packages --group dev

# 5. Start fresh infrastructure
make infra-up

# 6. Wait for Postgres health check
docker compose -f infra/docker-compose.yml ps

# 7. Run migrations
make migrate

# 8. Verify
make test
make lint
```
