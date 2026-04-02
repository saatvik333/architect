# On-Call Runbook

## Escalation Contacts

> **Update with actual team contacts before going to production.**

| Role | Contact | Backup |
|------|---------|--------|
| On-call engineer | TBD | TBD |
| Engineering lead | TBD | TBD |
| Infrastructure | TBD | TBD |

## Severity Definitions

| Severity | Description | Examples |
|----------|-------------|----------|
| **P0 - Critical** | System fully down or data loss occurring | All services unreachable; database corruption; security breach |
| **P1 - High** | Major feature broken, no workaround | Task execution pipeline stuck; agent loop failing for all users |
| **P2 - Medium** | Feature degraded, workaround exists | Slow query performance; single service intermittently failing |
| **P3 - Low** | Minor issue, cosmetic or non-urgent | Dashboard UI glitch; log noise; non-critical metric gap |

## Response Time Expectations

| Severity | Acknowledge | Begin investigation | Resolution target |
|----------|-------------|--------------------|--------------------|
| P0 | 5 minutes | 15 minutes | 1 hour |
| P1 | 15 minutes | 30 minutes | 4 hours |
| P2 | 1 hour | Next business day | 3 business days |
| P3 | Next business day | Best effort | Next sprint |

## Common Alert Responses

- **Service health check failing** -- See [service-operations.md](service-operations.md) for per-service restart and debug steps.
- **Database connection errors** -- See [deployment.md](deployment.md) for Postgres troubleshooting.
- **High error rate / latency** -- See [observability.md](observability.md) for Grafana dashboards and Jaeger trace lookup.
- **Security alerts** -- See [incident-response.md](incident-response.md) for the security incident playbook.
- **Docker / container issues** -- See [docker-security.md](docker-security.md) for container runtime troubleshooting.

## Rollback Procedure

1. **Confirm the issue** -- verify the alert is real via Grafana dashboards and service logs.
2. **Notify the team** -- post in the incident channel with severity and affected services.
3. **Trigger rollback** -- run the Deploy workflow with a `rollback_ref`:
   ```
   gh workflow run deploy.yml \
     -f environment=production \
     -f rollback_ref=<previous-good-ref>
   ```
   Alternatively, SSH to the host and rollback manually:
   ```bash
   cd /opt/architect
   git checkout <previous-good-ref>
   docker compose --env-file .env -f infra/docker-compose.yml up -d
   uv run alembic upgrade head
   python scripts/check-health.py --timeout 60
   ```
4. **Verify recovery** -- confirm health checks pass and error rates return to normal.
5. **Write incident report** -- document root cause, timeline, and follow-up actions.
