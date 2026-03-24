# Deployment Runbook

## Prerequisites

- Docker and Docker Compose installed
- Access to the deployment target (staging/production server)
- `.env` file with all required credentials (see `scripts/dev-setup.sh`)

## Local Development

```bash
# First time setup
./scripts/dev-setup.sh

# Start infrastructure + services
make run-all

# Stop everything
make stop-all
```

## Staging Deployment

### Via GitHub Actions (Recommended)

1. Go to Actions > "Deploy" workflow
2. Click "Run workflow"
3. Select `staging` environment
4. Enter the git ref (branch, tag, or SHA)
5. Click "Run workflow"
6. Monitor the workflow run for completion

### Manual Staging Deploy

```bash
# SSH to staging server
ssh staging.architect.internal

# Pull latest code
cd /opt/architect
git pull origin main

# Apply infrastructure changes
docker compose -f infra/docker-compose.yml up -d

# Run migrations
ARCHITECT_DATABASE_URL=<staging-dsn> uv run alembic -c libs/architect-db/alembic.ini upgrade head

# Restart services
make stop-all && make run-all

# Verify health
curl -sf http://localhost:8000/health | jq .
```

## Production Deployment

### Pre-Deployment Checklist

- [ ] All CI checks pass on the commit being deployed
- [ ] Staging deployment tested and verified
- [ ] Database migration reviewed (if any)
- [ ] Rollback plan documented
- [ ] On-call engineer notified

### Deploy via GitHub Actions

1. Go to Actions > "Deploy" workflow
2. Select `production` environment
3. This requires **manual approval** (GitHub environment protection)
4. An approver must click "Approve" before deployment proceeds

### Post-Deploy Verification

```bash
# Check all services
curl -sf http://localhost:8000/health | jq .

# Verify recent tasks still work
curl -sf http://localhost:8000/api/v1/tasks | jq '.[:3]'

# Check for errors in last 5 minutes
docker compose logs --since 5m 2>&1 | grep -c ERROR
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | Database password (shared with docker-compose) |
| `ARCHITECT_PG_PASSWORD` | Yes | Must match `POSTGRES_PASSWORD` |
| `REDIS_PASSWORD` | Yes | Redis authentication password |
| `ARCHITECT_REDIS_PASSWORD` | Yes | Must match `REDIS_PASSWORD` |
| `ARCHITECT_GATEWAY_API_KEYS_RAW` | Recommended | Comma-separated API keys |
| `ARCHITECT_CLAUDE_API_KEY` | For LLM features | Anthropic API key |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional | OpenTelemetry collector (e.g. http://jaeger:4317) |

## Horizontal Scaling

### Services That Scale Horizontally

- **API Gateway**: Stateless, scale behind a load balancer
- **Spec Engine**: Stateless LLM calls
- **Multi-Model Router**: Stateless routing logic
- **Codebase Comprehension**: Stateless analysis (in-memory index is per-instance)

### Services That Require Coordination

- **Task Graph Engine**: Uses `DistributedSchedulerLock` with Redis for coordination
- **World State Ledger**: Uses `SELECT ... FOR UPDATE` for OCC — safe with multiple instances
- **Execution Sandbox**: Session persistence via DB — multiple instances can manage different containers

### Services That Are Single-Instance

- **Evaluation Engine**: Stateless but typically one evaluator per task
- **Coding Agent**: Stateless per-task execution
- **Agent Comm Bus**: NATS handles distribution; multiple instances OK
