# ADR-005: API Authentication Strategy

**Status:** Accepted

**Date:** 2026-03-15

---

## Context

All API endpoints exposed by the API Gateway are currently unauthenticated (finding S-C2, CVSS 9.1). Any network-reachable client can submit tasks, read state, cancel work, and publish messages to the agent communication bus without presenting any credentials.

This is acceptable during local development but is a blocking issue for any non-local deployment. The system needs an authentication layer before production use.

The threat model includes:

1. **Unauthorized task submission:** An attacker could submit expensive LLM-backed tasks, consuming token budget.
2. **State manipulation:** Unauthenticated access to the World State Ledger allows reading sensitive project data and submitting rogue proposals.
3. **Service disruption:** The cancel endpoint and message bus publish endpoint allow an attacker to disrupt in-progress work.

Internal service-to-service communication (between the 9 ARCHITECT services) is not exposed externally -- it flows over the Docker Compose network via Temporal, NATS, and direct HTTP calls. However, it is also unauthenticated, which becomes a concern if the network boundary is ever relaxed.

## Decision

Implement API authentication in three phases, matching the project's existing phase structure:

### Phase 1 (immediate): API key authentication on the gateway

- The API Gateway validates a bearer token on every inbound request.
- Tokens are checked against a configurable allowlist stored in the `ARCHITECT_GATEWAY_API_KEYS` environment variable (comma-separated list of valid keys).
- Requests without a valid `Authorization: Bearer <key>` header receive HTTP 401.
- Health check endpoints (`GET /health`, `GET /ready`) are exempt from authentication.
- API keys are opaque strings (recommended: 32+ character random hex). No user identity is encoded in the key.

### Phase 2 (Phase 3 of ARCHITECT): Service-to-service JWT

- Internal services authenticate to each other using short-lived JWTs signed with a shared secret or asymmetric keypair.
- The gateway mints a JWT for downstream service calls, encoding the originating API key identity and request correlation ID.
- Services validate the JWT on every inbound request, rejecting expired or unsigned tokens.
- This enables per-service audit trails and prepares for role-based access control.

### Phase 3 (Phase 4 of ARCHITECT): Mutual TLS between services

- All inter-service communication uses mTLS with certificates issued by an internal CA.
- Each service has its own certificate, enabling fine-grained network policies (e.g., only the gateway can call the spec engine).
- Certificate rotation is automated via a sidecar or init container.
- This eliminates the shared-network trust assumption entirely.

### Alternatives considered

1. **OAuth 2.0 / OIDC from the start:** Full-featured but heavyweight for a system that currently has no user database and no browser-based clients. The CLI and API Gateway are the only external consumers. OAuth adds significant operational complexity (token server, refresh flows, PKCE) for a single-user or small-team system. Can be adopted later when the Human Interface (Phase 5) introduces a web dashboard with user accounts.

2. **mTLS everywhere from the start:** Provides the strongest guarantees but requires a certificate authority, certificate distribution, and rotation automation. Operational overhead is disproportionate for local and single-machine deployments. Better suited for Phase 4 when the system is deployed across multiple hosts.

3. **Network-level isolation only (no application auth):** Relies on Docker network boundaries and firewall rules. Insufficient because a single container compromise or misconfigured port mapping would expose the entire system. Defense-in-depth requires application-level authentication in addition to network controls.

## Consequences

### Positive

- **Immediate risk reduction:** API key auth on the gateway eliminates the CVSS 9.1 unauthenticated access finding with minimal implementation effort.
- **Backward compatible:** Existing CLI and scripts only need to add an `Authorization` header. No protocol changes required.
- **Progressive hardening:** Each phase adds a layer of authentication without requiring a rewrite of previous phases.
- **Audit trail:** API keys can be logged (hashed) with each request, enabling attribution of actions to specific callers.

### Negative

- **API keys are shared secrets:** If a key is leaked, it grants full access until rotated. There is no per-user identity or fine-grained permissions in Phase 1.
- **No rate limiting per key:** Phase 1 does not distinguish between keys for rate limiting purposes. All keys share the same budget and access level.
- **Environment variable storage:** Storing keys in environment variables is standard practice but requires care to avoid logging them or exposing them in process listings. A secrets manager would be more robust but adds infrastructure dependency.
- **Internal traffic remains unauthenticated until Phase 2:** A compromised container can still call other services directly. This is mitigated by the Docker network boundary but is not a complete defense.
