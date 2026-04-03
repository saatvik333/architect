# ARCHITECT Security Audit Tracker

**Consolidated from:** `phase3-security-audit.md` (2026-03-26) and `phase3-security-audit-comprehensive.md` (2026-03-31)

This document tracks all unique security findings from both Phase 3 audits, their remediation status, and relevant commit references. Findings are deduplicated and organized by severity.

---

## Summary

| Severity | Total | Remediated | Open | Accepted Risk |
| --- | --- | --- | --- | --- |
| Critical | 8 | 5 | 3 | 0 |
| High | 8 | 3 | 5 | 0 |
| Medium | 11 | 0 | 9 | 2 |
| Low | 8 | 0 | 4 | 4 |

---

## Critical Findings

| ID | Title | Source | Status | Commit / Notes |
| --- | --- | --- | --- | --- |
| C-SSRF | SSRF bypass via DNS rebinding and redirect following in `example_miner.py` / `doc_fetcher.py` | Audit 1 (C-02), Audit 2 (C-1) | Remediated | `2a3545c` -- SSRF redirect protection; `doc_fetcher.py` uses `follow_redirects=False` and IP validation |
| C-WS-AUTH | WebSocket authentication accepts any non-empty token / no auth | Audit 1 (C-04), Audit 2 (C-2) | Remediated | `552b34e` -- Token validated against `ARCHITECT_WS_TOKEN` via `hmac.compare_digest`; fail-closed when unset |
| C-SQL | No ORM models for knowledge tables -- raw SQL patterns | Audit 1 (C-03) | Remediated | `dbbf566` -- SQL injection protections; parameterized queries |
| C-BUDGET-MEM | In-memory budget state without persistence -- enforcement bypass on restart | Audit 1 (C-05) | Remediated | Noted as remediated in audit 1 -- `BudgetTracker` now loads/persists state via Postgres |
| C-TEMPORAL | Temporal activities create fresh state on each invocation | Audit 1 (C-06) | Remediated | Noted as remediated in audit 1 -- activities now use shared singleton `BudgetTracker` |
| C-LLM-INJECT | LLM prompt injection -- missing `<user_input>` delimiters across Knowledge & Memory | Audit 1 (C-01), Audit 2 (H-4) | Open | All four LLM integration points (`heuristic_engine.py`, `compression.py`, `pattern_extractor.py`, `example_miner.py`) interpolate user-controllable data without delimiter tags. Partially addressed by `f4684e4` (LLM output validation) but input-side injection remains. |
| C-NO-AUTHZ | Missing authorization on all Phase 3 service endpoints | Audit 2 (C-3) | Open | Services bind to `0.0.0.0` and expose ports directly. Budget mutation, escalation resolution, and knowledge injection endpoints have no auth when accessed outside the gateway. |
| C-ESCALATION-ID | Unvalidated escalation ID path parameters enable data manipulation | Audit 2 (C-5) | Open | Combined with C-NO-AUTHZ, allows unauthenticated resolution of any escalation. Identity impersonation partially addressed by `20cfd19` (resolved_by now prefers `X-Authenticated-User` header). |

## High Findings

| ID | Title | Source | Status | Commit / Notes |
| --- | --- | --- | --- | --- |
| H-DUP-VOTE | Approval gate voting has no duplicate vote prevention | Audit 1 (H-02) | Remediated | Noted as remediated in audit 1 -- routes.py checks existing votes, returns HTTP 409. Race condition remains (no DB unique constraint). FK/unique constraints addressed in `c1fba50`. |
| H-WS-LIMIT | Unbounded WebSocket connections -- denial of service | Audit 1 (H-06) | Remediated | Noted as remediated in audit 1 -- `max_connections=100` with close code 4002 |
| H-GATEWAY-FAILOPEN | API Gateway fail-open when auth backend unavailable | Cross-ref | Remediated | `bb6ea3e` -- API gateway fail-open fix |
| H-NO-SVC-AUTH | No authentication on any Phase 3 API endpoint | Audit 1 (H-01), Audit 2 (C-3) | Open | Overlaps with C-NO-AUTHZ. No per-service auth middleware. Gateway auth only. |
| H-RESOLVE-AUTHZ | Escalation resolution has no authorization check -- `resolved_by` is free-form | Audit 1 (H-03) | Open | `resolved_by` not bound to authenticated identity. Partially mitigated by `20cfd19` (prefers `X-Authenticated-User` header). |
| H-SUPPLY-CHAIN | Trivy GitHub Action pinned to `@master` -- supply chain risk | Audit 2 (H-1) | Open | Mutable reference in `.github/workflows/release.yml`. Should pin to commit SHA. |
| H-GRAFANA-PW | Grafana password falls back to `admin` default | Audit 2 (H-2) | Open | `infra/docker-compose.yml` uses `${GRAFANA_PASSWORD:-admin}`. Should use fail-fast `${GRAFANA_PASSWORD:?error}`. |
| H-LLM-OUTPUT | LLM output not validated before storage (heuristic actions, patterns) | Audit 1 (H-07) | Open | LLM-generated JSON stored without semantic validation. Partially addressed by `f4684e4` (LLM output validation) but action field allowlisting not implemented. |

## Medium Findings

| ID | Title | Source | Status | Notes |
| --- | --- | --- | --- | --- |
| M-WS-BROADCAST | WebSocket broadcast leaks all event data to all connected clients | Audit 1 (M-08), Audit 2 (M-1) | Open | No topic filtering or access control on broadcasts. |
| M-UNBOUNDED-QUERY | Unbounded query results in knowledge store (`/heuristics`, `/meta-strategies`) | Audit 2 (M-2) | Open | No `limit` parameter on several list endpoints. |
| M-ERROR-DISCLOSURE | Information disclosure in error messages (DNS errors, SSRF blocks) | Audit 2 (M-3) | Open | Internal details leaked in error responses. |
| M-BUDGET-VALIDATION | Missing upper bound validation on budget consumption recording | Audit 2 (M-4) | Open | No per-request cap on `tokens` or `cost_usd`. |
| M-VOTE-RACE | Approval gate vote duplicate check is not atomic (race condition) | Audit 2 (M-5) | Open | No `(gate_id, voter)` unique constraint at DB level. |
| M-TEMPORAL-TLS | Temporal worker connects without TLS or authentication | Audit 1 (D-03), Audit 2 (M-6) | Open | All Temporal traffic in cleartext. |
| M-HARDCODED-URLS | Hardcoded internal service URLs in config defaults and Temporal activities | Audit 1 (M-01) | Open | Temporal activities accept `service_url` from workflow input. |
| M-RATE-LIMIT | No rate limiting on Phase 3 service endpoints | Audit 1 (M-02), Audit 2 (H-3) | Open | Direct access to services bypasses gateway rate limiting. |
| M-BROAD-EXCEPT | Broad exception handling masks errors across all three services | Audit 1 (M-03), Audit 2 (L-5) | Open | Silent fallbacks for DB failures, Temporal failures. |
| M-CORS | No CORS configuration on Phase 3 services | Audit 1 (M-05) | Accepted Risk | Services intended to be accessed via API Gateway which handles CORS. Direct access is a deployment concern. |
| M-HTML-PARSER | BeautifulSoup HTML parser exploitable via deeply nested or large documents | Audit 1 (M-06) | Accepted Risk | Low likelihood in practice; `html.parser` is the safest stdlib option. |

## Low Findings

| ID | Title | Source | Status | Notes |
| --- | --- | --- | --- | --- |
| L-DOCKER-PORTS | Docker Compose ports exposed to all interfaces (`0.0.0.0`) | Audit 2 (L-1) | Open | Development convenience. Should bind to `127.0.0.1` in production. |
| L-LOCALSTORAGE | API key stored in `localStorage` (Dashboard) | Audit 2 (L-2) | Open | Vulnerable to XSS exfiltration. Prefer `httpOnly` cookies. |
| L-WS-URL | Hardcoded WebSocket URL derivation in Dashboard | Audit 2 (L-3) | Open | Token exposed in URL query string. |
| L-ENV-EXAMPLE | `.env.example` contains placeholder API key pattern (`sk-ant-...`) | Audit 2 (L-4) | Open | Reveals key format. Replace with empty value. |
| L-HEALTH | Health endpoints report healthy regardless of dependency status | Audit 1 (L-01) | Accepted Risk | Health checks now return `DEGRADED` when dependencies unavailable. Remaining gap is DB ping. |
| L-UPTIME | `time.monotonic()` for uptime set at import time | Audit 1 (L-02) | Accepted Risk | Minor inaccuracy. Set in lifespan manager would be more accurate. |
| L-CUSTOM-INPUT | Escalation `custom_input` accepts arbitrary data with no size/depth limits | Audit 1 (M-07) | Accepted Risk | FastAPI/Starlette enforce default body size limits. Deep nesting is low risk. |
| L-LOG-INJECTION | `resolved_by` / `voter` fields logged without sanitization | Audit 1 (M-04) | Accepted Risk | structlog handles escaping. Risk is minimal with structured logging. |

---

## Remediation Commit Reference

| Commit | Description |
| --- | --- |
| `552b34e` | WebSocket token-based authentication with `hmac.compare_digest` |
| `dbbf566` | SQL injection protections and parameterized queries |
| `20cfd19` | Identity impersonation fix -- `resolved_by` prefers authenticated header |
| `bb6ea3e` | API Gateway fail-open fix |
| `c1fba50` | Foreign key and unique constraints |
| `2a3545c` | SSRF redirect protection |
| `f4684e4` | LLM output validation |

---

## Next Remediation Priorities

1. **C-LLM-INJECT** (Critical) -- Add `<user_input>` delimiter tags to all LLM prompts in Knowledge & Memory. Low effort, high impact.
2. **C-NO-AUTHZ** (Critical) -- Add per-service auth middleware or bind services to `127.0.0.1`. High effort.
3. **H-SUPPLY-CHAIN** (High) -- Pin Trivy action to commit SHA. Low effort.
4. **H-GRAFANA-PW** (High) -- Change to fail-fast env var syntax. Low effort.
5. **M-BUDGET-VALIDATION** (Medium) -- Add upper bounds on consumption request fields. Low effort.
6. **M-RATE-LIMIT** (Medium) -- Add per-endpoint rate limiting. Medium effort.
