# Incident Response Runbook

## Severity Levels

| Level | Description | Response Time | Examples |
|-------|------------|---------------|----------|
| **SEV-1** | System down, all users affected | Immediate | Complete service outage, data loss |
| **SEV-2** | Major feature broken, workaround exists | < 30 min | Task submission failing, eval engine down |
| **SEV-3** | Minor feature broken, limited impact | < 2 hours | Single agent failing, dashboard slow |
| **SEV-4** | Cosmetic or non-critical issue | Next business day | Log formatting, UI alignment |

## First Response Checklist

1. **Assess impact**: Which services are affected? Check `/health` endpoints.
2. **Check infrastructure**: Are Postgres, Redis, Temporal, NATS all healthy?
3. **Check recent changes**: What was the last deployment? (`git log --oneline -5`)
4. **Gather evidence**: Collect logs, traces, metrics before making changes.

## Service Health Check

```bash
# Check all services at once
for port in 8000 8001 8003 8007 8008 8009 8010 8011 8012 8013; do
    echo -n "Port $port: "
    curl -sf http://localhost:$port/health | jq -r '.status' 2>/dev/null || echo "DOWN"
done
```

## Infrastructure Health

```bash
# Postgres
docker exec $(docker ps -qf name=postgres) pg_isready -U architect

# Redis
docker exec $(docker ps -qf name=redis) redis-cli -a $REDIS_PASSWORD ping

# Temporal
curl -sf http://localhost:8080/api/v1/namespaces/architect | jq '.namespaceInfo.state'

# NATS
curl -sf http://localhost:8222/healthz
```

## Common Scenarios

### Service Won't Start

1. Check Docker logs: `docker compose -f infra/docker-compose.yml logs <service>`
2. Verify `.env` has all required credentials
3. Check port conflicts: `lsof -i :<port>`
4. Verify database is migrated: `uv run alembic -c libs/architect-db/alembic.ini current`

### Database Connection Exhaustion

1. Check active connections: `SELECT count(*) FROM pg_stat_activity;`
2. Check per-service: `SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1;`
3. If exhausted: restart services one at a time (they'll acquire new connections)
4. Long-term: adjust `ARCHITECT_PG_POOL_SIZE` (default: 3 per service, max 8 total = 72)

### Temporal Workflow Stuck

1. Open Temporal UI: http://localhost:8080
2. Find the stuck workflow by ID
3. Check workflow history for errors
4. If retryable: use "Reset" to replay from a known-good point
5. If unrecoverable: "Terminate" the workflow

### Redis Memory Exhaustion

1. Check usage: `redis-cli -a $REDIS_PASSWORD INFO memory | grep used_memory_human`
2. Check stream sizes: `redis-cli -a $REDIS_PASSWORD XLEN architect:<stream_name>`
3. Streams are auto-capped at 10,000 entries (MAXLEN in EventPublisher)
4. Clear stale data: `redis-cli -a $REDIS_PASSWORD FLUSHDB` (CAUTION: clears cache)

### High Error Rate After Deploy

1. Check error rate in logs: `docker compose logs --since 5m | grep -c ERROR`
2. Compare with pre-deploy baseline
3. If error rate > 2x baseline: **roll back immediately**
4. Rollback: `git revert <commit> && deploy`

## Rollback Procedure

```bash
# 1. Identify the last known-good commit
git log --oneline -10

# 2. Revert to it
git checkout <good-commit-sha>

# 3. Redeploy
# For docker-compose deployments:
docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml up -d

# 4. Verify health
curl -sf http://localhost:8000/health | jq .
```

## Post-Incident

After resolution:
1. Write a brief post-mortem (what happened, root cause, fix, prevention)
2. Update this runbook if new scenarios were encountered
3. Create follow-up issues for any gaps discovered
