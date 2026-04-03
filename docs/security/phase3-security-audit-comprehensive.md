> **SUPERSEDED**: This document has been consolidated into [security-audit-tracker.md](security-audit-tracker.md), which tracks remediation status across all findings.

# ARCHITECT Phase 3 -- Comprehensive Security Audit

**Audit Date**: 2026-03-31
**Auditor**: Security Review (Automated + Manual Analysis)
**Scope**: All uncommitted changes in Phase 3 services (Knowledge & Memory, Economic Governor, Human Interface), Dashboard extensions, infrastructure, and CI/CD
**Methodology**: OWASP Top 10 (2021), OWASP ASVS 4.0, CWE/SANS Top 25, CVSS 3.1 scoring

---

## Executive Summary

This audit identified **5 Critical**, **4 High**, **6 Medium**, and **5 Low** severity findings across the Phase 3 codebase. The most significant issues are SSRF bypass via DNS rebinding and redirect following in `example_miner.py`, absent WebSocket authentication, missing authorization on all Phase 3 service endpoints, a supply-chain risk in the CI/CD pipeline, and default credentials in infrastructure configuration.

Several findings from the Phase 1 review (C-1, C-2, L-7, L-8) remain partially or fully unresolved.

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 5     | Open   |
| High     | 4     | Open   |
| Medium   | 6     | Open   |
| Low      | 5     | Open   |

---

## Critical Findings

### C-1: SSRF Bypass via DNS Rebinding and Redirect Following in example_miner.py

**Severity**: Critical (CVSS 9.1)
**CWE**: CWE-918 (Server-Side Request Forgery)
**Location**: `services/knowledge-memory/src/knowledge_memory/example_miner.py:50`
**Phase 1 Ref**: C-1 (partially remediated -- `doc_fetcher.py` fixed, but `example_miner.py` introduced a new bypass path)

**Description**: The `mine_examples()` function creates its own `httpx.AsyncClient` with `follow_redirects=True`, completely bypassing the SSRF protections in `doc_fetcher.py`. While `fetch_documentation()` is called inside this context, the pre-constructed client with redirect-following enabled is passed to it, overriding the safe client that `fetch_documentation()` creates internally (which has `follow_redirects=False` on line 124).

The `validate_url()` function in `doc_fetcher.py` performs DNS resolution at validation time, but DNS rebinding attacks can return a safe IP on the first lookup and an internal IP on the subsequent connection. With `follow_redirects=True`, an attacker-controlled server can also respond with a 302 redirect to an internal service URL, bypassing the initial validation entirely.

**Proof of Concept**:
```
POST /api/v1/acquire
{
  "topic": "exploit",
  "source_urls": ["https://attacker.com/redirect-to-internal"]
}
```

Where `attacker.com/redirect-to-internal` returns:
```
HTTP/1.1 302 Found
Location: http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

The redirect bypasses `validate_url()` because the initial URL resolves to a public IP. The `follow_redirects=True` client then follows the redirect to the cloud metadata service.

**Remediation**:
1. Remove `follow_redirects=True` from the httpx client in `example_miner.py`.
2. Apply a transport-level hook to validate each resolved IP before connection. httpx supports `event_hooks` for this purpose.
3. Alternatively, use a custom `httpx.AsyncHTTPTransport` that validates the resolved address at connection time (TOCTOU-safe).

```python
# example_miner.py line 50 -- remove follow_redirects
async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http_client:
```

For TOCTOU-safe protection against DNS rebinding:
```python
import httpcore

class SSRFSafeTransport(httpcore.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        # Resolve and validate IP at connection time
        host = request.url.host
        addr_infos = socket.getaddrinfo(host, request.url.port)
        for _, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    raise ValueError(f"Blocked: {ip}")
        return await super().handle_async_request(request)
```

---

### C-2: WebSocket Authentication Accepts Any Non-Empty Token

**Severity**: Critical (CVSS 9.1)
**CWE**: CWE-287 (Improper Authentication)
**Location**: `services/human-interface/src/human_interface/api/routes.py:541-545`
**Phase 1 Ref**: C-2 (unresolved)

**Description**: The WebSocket endpoint checks only that a `token` query parameter exists and is non-empty. There is no actual token validation -- any string is accepted.

```python
token = websocket.query_params.get("token")
if not token:
    await websocket.close(code=4001, reason="Unauthorized")
    return
```

Any unauthenticated client can connect with `?token=anything` and receive all real-time escalation data, approval gate updates, and system activity broadcasts. This is a complete authentication bypass.

**Attack Scenario**: An attacker connects to `ws://host:8016/api/v1/ws?token=x` and receives all escalation data, including security-critical escalations, budget information, and approval gate decisions in real time.

**Remediation**:
```python
@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    config: HumanInterfaceConfig = Depends(get_config),
) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Validate the token against the configured API keys
    if not config.validate_ws_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket)
    # ...
```

---

### C-3: Missing Authorization on All Phase 3 Service Endpoints

**Severity**: Critical (CVSS 8.6)
**CWE**: CWE-862 (Missing Authorization)
**Location**: All route files across Phase 3 services

**Description**: None of the Phase 3 service endpoints implement authorization checks. While the API Gateway provides Bearer token auth for external traffic, the services themselves bind to `0.0.0.0` and expose their ports directly. The Phase 3 services (ports 8014, 8015, 8016) are accessible without authentication when reached directly, bypassing the gateway.

The Economic Governor's budget endpoints (`POST /api/v1/budget/record-consumption`, `POST /api/v1/budget/allocate`) are particularly sensitive -- an attacker with network access can drain the budget or manipulate enforcement levels. Similarly, `POST /api/v1/escalations/{id}/resolve` allows unauthenticated resolution of security-critical escalations.

**Affected Endpoints (selection of highest-risk)**:
- `POST /api/v1/budget/record-consumption` (economic-governor:8015) -- manipulate budget
- `POST /api/v1/budget/allocate` (economic-governor:8015) -- allocate arbitrary budget
- `POST /api/v1/escalations/{id}/resolve` (human-interface:8016) -- resolve security escalations
- `POST /api/v1/approval-gates/{id}/vote` (human-interface:8016) -- approve deployments
- `POST /api/v1/knowledge` (knowledge-memory:8014) -- inject malicious knowledge

**Remediation**:
1. Bind services to `127.0.0.1` instead of `0.0.0.0` in non-container deployments, or use network policies in Kubernetes.
2. Implement per-service authentication middleware that validates internal service tokens or mTLS certificates.
3. Add role-based authorization to sensitive endpoints (budget mutation, escalation resolution, approval voting).

---

### C-4: Self-Referential HTTP in Temporal Activities Bypasses API Auth

**Severity**: Critical (CVSS 8.1)
**CWE**: CWE-441 (Unintended Proxy or Intermediary)
**Location**: `services/economic-governor/src/economic_governor/enforcer.py:46`, `services/human-interface/src/human_interface/api/routes.py:479-509`
**Phase 1 Ref**: A-H2

**Description**: The Human Interface `get_progress()` endpoint (line 479) makes HTTP requests to other services (task graph at `config.task_graph_url`, economic governor at `config.economic_governor_url`) without authentication headers. These are internal service-to-service calls that bypass the API Gateway's Bearer token validation.

Similarly, the Enforcer creates an unauthenticated `httpx.AsyncClient` (line 53) for inter-service communication. If any of these services are exposed externally (which they are, bound to `0.0.0.0`), an attacker can proxy requests through them.

**Remediation**:
1. Implement internal service-to-service authentication using signed JWTs or mTLS.
2. Add a shared internal auth token validated by a middleware in each service.
3. Configure network segmentation so internal service ports are not reachable from external networks.

---

### C-5: Unvalidated Escalation ID Path Parameters Enable Data Manipulation

**Severity**: Critical (CVSS 8.2)
**CWE**: CWE-20 (Improper Input Validation) + CWE-862 (Missing Authorization)
**Location**: `services/human-interface/src/human_interface/api/routes.py:252-303`

**Description**: The `resolve_escalation` endpoint accepts an arbitrary `escalation_id` string as a path parameter and passes it directly to the repository's `resolve()` method. Combined with the complete absence of authorization (C-3), any network-adjacent attacker can resolve any escalation -- including security-critical ones -- by guessing or enumerating IDs.

The `resolved_by` field in the request body is a free-text string with no identity verification. An attacker can claim to be any user.

```python
async def resolve_escalation(
    escalation_id: str,        # No type validation against EscalationId pattern
    body: ResolveEscalationRequest,  # resolved_by is arbitrary text
    ...
```

**Attack Scenario**: An attacker iterates escalation IDs (they use a predictable UUID format with `esc-` prefix) and resolves security-critical escalations with arbitrary decisions.

**Remediation**:
1. Add authentication to identify the resolving user.
2. Validate that `resolved_by` matches the authenticated identity.
3. Add type validation on `escalation_id` to match the `EscalationId` pattern.
4. Implement audit logging for all escalation state transitions.

---

## High Findings

### H-1: Supply Chain Risk -- Trivy Action Pinned to @master

**Severity**: High (CVSS 7.5)
**CWE**: CWE-829 (Inclusion of Functionality from Untrusted Control Sphere)
**Location**: `.github/workflows/release.yml:60`
**Phase 1 Ref**: L-8

**Description**: The Trivy vulnerability scanning action is pinned to the `@master` branch tag rather than a specific commit SHA. A compromise of the `aquasecurity/trivy-action` repository would inject arbitrary code into every release build. This action runs with `contents: write` and `packages: write` permissions, allowing an attacker to modify releases and push malicious container images.

```yaml
- name: Scan container image for vulnerabilities
  uses: aquasecurity/trivy-action@master  # Mutable reference
```

**Remediation**: Pin to a specific commit SHA:
```yaml
- name: Scan container image for vulnerabilities
  uses: aquasecurity/trivy-action@062f2592684a31eb3aa050cc61bb940c1f1048f0  # v0.28.0
```

---

### H-2: Grafana Default Password Fallback

**Severity**: High (CVSS 7.2)
**CWE**: CWE-798 (Use of Hard-coded Credentials)
**Location**: `infra/docker-compose.yml:147`
**Phase 1 Ref**: L-7

**Description**: The Grafana admin password falls back to `admin` when the `GRAFANA_PASSWORD` environment variable is not set:

```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
```

This default is insecure. In development environments where `.env` may not include `GRAFANA_PASSWORD`, Grafana is accessible with `admin:admin`. Grafana provides full access to dashboards, data sources (including Prometheus metrics), and can be used to enumerate internal services.

**Remediation**: Use fail-fast syntax consistent with other services:
```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:?Set GRAFANA_PASSWORD in .env}
```

---

### H-3: No Rate Limiting on Phase 3 Service Endpoints

**Severity**: High (CVSS 7.0)
**CWE**: CWE-770 (Allocation of Resources Without Limits or Throttling)
**Location**: All Phase 3 service route files

**Description**: None of the Phase 3 services implement rate limiting. The API Gateway has rate limiting, but since services bind to `0.0.0.0` and can be accessed directly, an attacker can:

1. Flood the budget consumption endpoint to rapidly exhaust the project budget.
2. Spam escalation creation to overwhelm the human operator interface.
3. Abuse the knowledge query endpoint to perform denial-of-service against the database.
4. Flood WebSocket connections up to the `max_connections=100` limit (ws_manager.py:19).

**Remediation**:
1. Add per-endpoint rate limiting using `slowapi` or a custom middleware.
2. Implement per-IP connection rate limiting for WebSocket connections.
3. Add request size limits for knowledge entry content.

---

### H-4: LLM Prompt Injection via User-Controlled Content in Compression Pipeline

**Severity**: High (CVSS 7.3)
**CWE**: CWE-74 (Injection)
**Location**: `services/knowledge-memory/src/knowledge_memory/compression.py:155-186`, `services/knowledge-memory/src/knowledge_memory/pattern_extractor.py:79-111`, `services/knowledge-memory/src/knowledge_memory/heuristic_engine.py:114-145`

**Description**: The compression pipeline passes user-controlled observation content, pattern descriptions, and heuristic conditions to LLM prompts. While `<user_input>` delimiter tags are used (correctly following CLAUDE.md conventions), the content within observations originates from task execution events that include arbitrary agent output and error messages.

In `event_handler.py:86`, the observation description is constructed from user-controlled fields:
```python
description = f"Task {task_id} failed by {agent_id}: {data.error_message}"
```

This `error_message` flows into observations, then into clusters, and then into LLM prompts in `pattern_extractor.py:82`:
```python
f"- [{obs.get('observation_type', 'unknown')}] {obs.get('description', '')}"
```

An agent that injects adversarial content in its error messages can manipulate the patterns and heuristics derived by the compression pipeline, poisoning the learning system.

**Remediation**:
1. Sanitize observation descriptions before storage -- strip control characters, truncate to a maximum length.
2. Add content validation for `error_message` in `TaskFailedPayload`.
3. Implement output validation on LLM responses before storing as heuristics.
4. Add a confidence floor for auto-applied heuristics.

---

## Medium Findings

### M-1: WebSocket Broadcast Leaks All Event Data to All Connected Clients

**Severity**: Medium (CVSS 6.5)
**CWE**: CWE-200 (Exposure of Sensitive Information)
**Location**: `services/human-interface/src/human_interface/ws_manager.py:57-84`

**Description**: The `broadcast()` method sends every message to all connected WebSocket clients with no topic filtering or access control. This means all connected clients receive all escalation data (including security-critical escalations), approval gate decisions, and system activity regardless of their authorization level.

Combined with C-2 (trivial authentication bypass), this effectively makes all real-time operational data publicly accessible.

**Remediation**:
1. Implement topic-based subscriptions so clients only receive events they are authorized for.
2. Add per-connection authorization context to filter events by sensitivity level.
3. Redact sensitive fields (e.g., `reasoning`, `risk_if_wrong`) from broadcast payloads.

---

### M-2: Unbounded Query Results in Knowledge Store

**Severity**: Medium (CVSS 5.3)
**CWE**: CWE-400 (Uncontrolled Resource Consumption)
**Location**: `services/knowledge-memory/src/knowledge_memory/api/routes.py:70-104, 165-171, 294-299`

**Description**: Several knowledge store endpoints allow queries without adequate result limits:

- `GET /api/v1/heuristics` (line 165): No limit parameter, returns all active heuristics.
- `GET /api/v1/meta-strategies` (line 294): No limit parameter, returns all meta-strategies.
- `POST /api/v1/knowledge/query`: Has a `limit` field in the request body but its validation depends entirely on the `KnowledgeQuery` model. If the model does not enforce a maximum, the database query can return arbitrarily large result sets.

**Remediation**:
```python
@router.get("/api/v1/heuristics")
async def list_heuristics(
    domain: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ...
```

---

### M-3: Information Disclosure in Error Messages

**Severity**: Medium (CVSS 4.3)
**CWE**: CWE-209 (Generation of Error Message Containing Sensitive Information)
**Location**: Multiple locations

**Description**: Several error paths expose internal implementation details:

1. `doc_fetcher.py:63`: DNS resolution errors include the raw hostname and socket error:
   ```python
   raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}")
   ```

2. `doc_fetcher.py:75`: SSRF block messages reveal internal network topology:
   ```python
   raise ValueError(f"URL resolves to blocked internal address {ip} (in {network})")
   ```

3. FastAPI default error responses include full Pydantic validation errors with field names and types, which disclose the internal data model.

**Remediation**: Return generic error messages to clients and log detailed errors server-side:
```python
logger.warning("ssrf_blocked", url=url, resolved_ip=str(ip))
raise ValueError("URL validation failed")
```

---

### M-4: Missing Input Validation on Budget Consumption Recording

**Severity**: Medium (CVSS 5.9)
**CWE**: CWE-20 (Improper Input Validation)
**Location**: `services/economic-governor/src/economic_governor/api/routes.py:44-49`

**Description**: The `RecordConsumptionRequest` model validates that `tokens` and `cost_usd` are non-negative, but there is no upper bound validation. An attacker (or misbehaving agent) can submit extremely large values in a single request:

```python
class RecordConsumptionRequest(BaseModel):
    agent_id: str           # No format validation
    tokens: int = Field(ge=0)  # No upper bound
    cost_usd: float = Field(ge=0.0)  # No upper bound
```

A single request with `tokens=999999999999` would immediately push the budget past the halt threshold, shutting down all work.

**Remediation**:
```python
class RecordConsumptionRequest(BaseModel):
    agent_id: str = Field(pattern=r"^agent-[a-f0-9-]+$")
    tokens: int = Field(ge=0, le=10_000_000)  # Reasonable per-request cap
    cost_usd: float = Field(ge=0.0, le=100.0)  # Reasonable per-request cap
```

---

### M-5: Approval Gate Vote Decision Not Properly Constrained at ORM Level

**Severity**: Medium (CVSS 5.5)
**CWE**: CWE-20 (Improper Input Validation)
**Location**: `services/human-interface/src/human_interface/api/routes.py:438`

**Description**: While the `VoteRequest` model uses `Literal["approve", "deny"]` for the `decision` field, the logic at line 438 only handles these two specific strings with `if`/`elif`. Any other value that somehow bypasses Pydantic validation (e.g., via direct database manipulation or future refactoring that relaxes the constraint) would result in a vote being recorded without any state change to the gate, creating a phantom vote.

Additionally, the duplicate vote check (line 424-426) is not atomic -- under concurrent requests from the same voter, a race condition could allow multiple votes from a single voter.

```python
existing_votes = await vote_repo.get_by_gate(gate_id)
if any(v.voter == body.voter for v in existing_votes):
    # Race condition: two concurrent requests pass this check
```

**Remediation**:
1. Add a unique constraint on `(gate_id, voter)` in the database schema.
2. Add an `else` clause that raises `HTTPException(400)` for unrecognized decisions.
3. Use `SELECT ... FOR UPDATE` or equivalent pessimistic locking in the vote flow.

---

### M-6: Temporal Worker Connects Without TLS or Authentication

**Severity**: Medium (CVSS 5.3)
**CWE**: CWE-319 (Cleartext Transmission of Sensitive Information)
**Location**: `services/economic-governor/src/economic_governor/temporal/worker.py:51-54`

**Description**: The Temporal worker connects to the Temporal server without TLS or authentication:

```python
client = await Client.connect(
    config.architect.temporal.target,
    namespace=config.architect.temporal.namespace,
)
```

All Temporal traffic (workflow data, activity parameters, budget information) is transmitted in cleartext. An attacker on the same network can intercept budget data, consumption records, and enforcement decisions.

**Remediation**: Configure TLS for Temporal connections:
```python
client = await Client.connect(
    config.architect.temporal.target,
    namespace=config.architect.temporal.namespace,
    tls=True,
)
```

---

## Low Findings

### L-1: Docker Compose Ports Exposed to All Interfaces

**Severity**: Low (CVSS 3.7)
**CWE**: CWE-668 (Exposure of Resource to Wrong Sphere)
**Location**: `infra/docker-compose.yml:10-11, 30-31, 55-56, etc.`

**Description**: All infrastructure services (Postgres, Redis, Temporal, NATS, Jaeger, Prometheus, Grafana) bind their ports to `0.0.0.0` via Docker's default port mapping (e.g., `"5432:5432"`). On hosts without a firewall, these services are accessible from any network.

While this is common in development, the docker-compose file appears to be the canonical deployment configuration. Postgres, Redis, and Temporal are particularly sensitive.

**Remediation**: Bind to localhost for development:
```yaml
ports:
  - "127.0.0.1:5432:5432"
```

---

### L-2: API Key Stored in localStorage (Dashboard)

**Severity**: Low (CVSS 3.3)
**CWE**: CWE-922 (Insecure Storage of Sensitive Information)
**Location**: `apps/dashboard/src/api/client.ts:16`

**Description**: The dashboard stores the auth token in `localStorage`:
```typescript
const token = localStorage.getItem('auth_token');
```

`localStorage` is accessible to any JavaScript running on the same origin. If the dashboard has any XSS vulnerability (or loads a compromised third-party dependency), the token can be exfiltrated.

**Remediation**: Use `httpOnly` cookies for auth tokens instead of `localStorage`. If cookies are not feasible, use `sessionStorage` (cleared on tab close) and implement token rotation.

---

### L-3: Hardcoded WebSocket URL Derivation in Dashboard

**Severity**: Low (CVSS 2.7)
**CWE**: CWE-1188 (Insecure Default Initialization)
**Location**: `apps/dashboard/src/pages/Activity.tsx:9`

**Description**: The WebSocket URL is derived from the API URL by replacing `http` with `ws`:
```typescript
const WS_URL = API_URL.replace(/^http/, 'ws') + '/api/v1/ws';
```

This does not append the authentication token. Based on the WebSocket endpoint code (C-2), a `token` query parameter is required. The dashboard's WebSocket connection will be rejected with code 4001 unless the `useWebSocket` hook adds the token separately.

If the hook does add a token, it may be exposed in browser history, server logs, and proxy logs via the URL query string.

**Remediation**: Pass the token via the WebSocket subprotocol header or via the first message after connection, not via the query string.

---

### L-4: `.env.example` Contains Placeholder API Key Pattern

**Severity**: Low (CVSS 2.0)
**CWE**: CWE-200 (Information Exposure)
**Location**: `.env.example:34`

**Description**: The `.env.example` file contains a partial API key pattern:
```
ARCHITECT_CLAUDE_API_KEY=sk-ant-...
```

While this is not a real key, it reveals the key format (`sk-ant-` prefix), making it easier for an attacker to recognize leaked keys in logs or repositories. Secret scanning tools may also flag this as a false positive, desensitizing developers.

**Remediation**:
```
ARCHITECT_CLAUDE_API_KEY=  # REQUIRED: Your Anthropic API key
```

---

### L-5: Exception Handling Silently Swallows Errors in Multiple Critical Paths

**Severity**: Low (CVSS 3.1)
**CWE**: CWE-390 (Detection of Error Condition Without Action)
**Location**: Multiple locations across all three services

**Description**: Several critical code paths use broad `except Exception` handlers that log warnings but continue execution. While this provides resilience, it can mask security-relevant failures:

- `services/economic-governor/src/economic_governor/budget_tracker.py:261`: Failed budget persistence is silently swallowed.
- `services/economic-governor/src/economic_governor/service.py:91-92`: Event subscriber failure is silently swallowed.
- `services/knowledge-memory/src/knowledge_memory/service.py:60-64`: Database connection failure is silently swallowed.
- `services/human-interface/src/human_interface/api/routes.py:189-193`: Temporal workflow start failure is silently swallowed.

If an attacker can cause persistent database failures (e.g., by exhausting connection pools), the budget tracker will continue operating in-memory without persistence, and enforcement actions will be lost on restart.

**Remediation**:
1. Emit metrics/alerts for each silently-handled exception (not just log warnings).
2. Add circuit-breaker patterns for critical dependencies.
3. Degrade to a safe state (e.g., HALT enforcement) if persistence is unavailable for an extended period.

---

## Configuration Security Assessment

### Infrastructure Services

| Service | Authentication | Encryption | Binding | Status |
|---------|---------------|------------|---------|--------|
| Postgres | Password (env var, fail-fast) | No TLS | 0.0.0.0:5432 | Partial |
| Redis | Password (env var, fail-fast) | No TLS | 0.0.0.0:6379 | Partial |
| Temporal | None | No TLS | 0.0.0.0:7233 | Weak |
| Temporal UI | None | No TLS | 0.0.0.0:8080 | Weak |
| NATS | None | No TLS | 0.0.0.0:4222 | Weak |
| Jaeger | None | No TLS | 0.0.0.0:4317 | Weak |
| Prometheus | None | No TLS | 0.0.0.0:9090 | Weak |
| Grafana | Password (default fallback) | No TLS | 0.0.0.0:3001 | Weak |

### Application Services

| Service | Port | Auth | AuthZ | Rate Limit | Security Headers |
|---------|------|------|-------|------------|------------------|
| Knowledge Memory | 8014 | None | None | None | Via gateway only |
| Economic Governor | 8015 | None | None | None | Via gateway only |
| Human Interface | 8016 | None (WS: trivial) | None | None | Via gateway only |
| API Gateway | 8000 | Bearer token | N/A | Yes | Yes |

---

## OWASP Top 10 (2021) Mapping

| # | Category | Findings | Severity |
|---|----------|----------|----------|
| A01 | Broken Access Control | C-3, C-5, M-1, M-5 | Critical |
| A02 | Cryptographic Failures | M-6 | Medium |
| A03 | Injection | C-1, H-4 | Critical/High |
| A04 | Insecure Design | C-4, H-3 | Critical/High |
| A05 | Security Misconfiguration | H-2, L-1, L-4 | High/Low |
| A06 | Vulnerable and Outdated Components | H-1 | High |
| A07 | Identification and Authentication Failures | C-2, L-2, L-3 | Critical/Low |
| A08 | Software and Data Integrity Failures | H-1 | High |
| A09 | Security Logging and Monitoring Failures | L-5 | Low |
| A10 | Server-Side Request Forgery | C-1 | Critical |

---

## Phase 1 Findings Status

| ID | Description | Status | Notes |
|----|------------|--------|-------|
| C-1 | SSRF in doc_fetcher | Partially Fixed | `doc_fetcher.py` now has `follow_redirects=False` and IP validation, but `example_miner.py` bypasses both protections by creating its own client with `follow_redirects=True` |
| C-2 | WebSocket accepts any token | Unresolved | TODO comment added but no implementation |
| L-7 | Grafana default password | Unresolved | Still uses `:-admin` fallback |
| L-8 | Trivy pinned to @master | Unresolved | No change |
| A-H2 | Self-referential HTTP bypasses auth | Unresolved | Same pattern present in Phase 3 services |

---

## Remediation Priority Matrix

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 (Immediate) | C-1: SSRF bypass via example_miner | Low | Critical |
| 2 (Immediate) | C-2: WebSocket auth bypass | Medium | Critical |
| 3 (Immediate) | C-3: Missing service-level auth | High | Critical |
| 4 (This Sprint) | H-1: Trivy pinned to @master | Low | High |
| 5 (This Sprint) | H-2: Grafana default password | Low | High |
| 6 (This Sprint) | C-4: Internal service auth bypass | High | Critical |
| 7 (This Sprint) | C-5: Escalation resolution without authz | Medium | Critical |
| 8 (This Sprint) | H-3: No rate limiting | Medium | High |
| 9 (Next Sprint) | H-4: LLM prompt injection | Medium | High |
| 10 (Next Sprint) | M-1 through M-6 | Varies | Medium |
| 11 (Backlog) | L-1 through L-5 | Low | Low |

---

## Summary of Positive Security Practices Observed

1. **SSRF validation in doc_fetcher.py**: Comprehensive blocklist of private networks, scheme validation, DNS resolution checking (though bypassed elsewhere).
2. **Fail-fast environment variables**: Postgres and Redis passwords use `${VAR:?error}` syntax in docker-compose.
3. **`<user_input>` delimiter tags**: LLM prompts correctly wrap user-controlled content in delimiter tags per CLAUDE.md conventions.
4. **Pydantic validation**: Request/response models use Pydantic with field constraints (`ge=0`, `le=1.0`, `Literal` types).
5. **WebSocket connection limits**: `WebSocketManager` enforces `max_connections=100`.
6. **Resource limits in Docker**: All containers have CPU and memory limits configured.
7. **Docker socket proxy**: Sandboxed Docker access via Tecnativa proxy with minimal permissions.
8. **Budget enforcement model**: The alert/restrict/halt escalation model is a sound design for preventing runaway cost.
