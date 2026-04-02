# WebSocket Protocol Specification

This document specifies the WebSocket protocol used by the Human Interface service (port 8016) for real-time event push to dashboard clients.

## Connection

**Endpoint:** `ws://<host>:8016/api/v1/ws`

**Secure endpoint:** `wss://<host>:8016/api/v1/ws` (when TLS is configured)

Connect with the authentication token as a query parameter:

```
ws://localhost:8016/api/v1/ws?token=<ARCHITECT_WS_TOKEN>
```

The server accepts the connection and begins broadcasting events. Clients do not send application-level messages; the connection is server-push only. The server reads from the client socket to keep the connection alive (ping/pong handling).

## Authentication

Authentication uses a shared token validated against the `ARCHITECT_WS_TOKEN` environment variable.

**Flow:**

1. Client connects with `?token=<value>` query parameter.
2. Server checks that the `token` parameter is present and non-empty.
3. Server checks that `ARCHITECT_WS_TOKEN` is configured in the environment. If not set, the connection is rejected (fail-closed).
4. Server performs constant-time comparison (`hmac.compare_digest`) of the provided token against the expected value.
5. On success, the connection is accepted and added to the broadcast pool.

**Rejection behavior:**

| Condition | Close Code | Reason |
| --- | --- | --- |
| Missing or empty `token` parameter | 4001 | `Unauthorized` |
| `ARCHITECT_WS_TOKEN` env var not set | 4003 | `WebSocket auth not configured` |
| Token does not match expected value | 4001 | `Invalid token` |

The fail-closed design ensures that if the token environment variable is accidentally unset, all connections are rejected rather than allowing unauthenticated access.

## Message Format

All messages are JSON objects with two top-level fields:

```json
{
  "type": "<event_type>",
  "data": { ... }
}
```

| Field | Type | Description |
| --- | --- | --- |
| `type` | string | Event type identifier (see Message Types below) |
| `data` | object | Event-specific payload |

Messages are serialized with `json.dumps(default=str)` so datetime objects are rendered as ISO 8601 strings.

## Message Types

The following event types are broadcast to all connected clients:

### `escalation_created`

Broadcast when a new escalation is created via `POST /api/v1/escalations`.

**Data:** Full `EscalationResponse` object including `id`, `source_agent_id`, `source_task_id`, `summary`, `category`, `severity`, `options`, `recommended_option`, `reasoning`, `risk_if_wrong`, `status`, `created_at`, `expires_at`.

### `escalation_resolved`

Broadcast when an escalation is resolved via `POST /api/v1/escalations/{id}/resolve`.

**Data:** Full `EscalationResponse` object with updated `status`, `resolved_by`, `resolution`, and `resolved_at` fields.

### `approval_gate_created`

Broadcast when a new approval gate is created via `POST /api/v1/approval-gates`.

**Data:** Full `ApprovalGateResponse` object including `id`, `action_type`, `resource_id`, `required_approvals`, `current_approvals`, `status`, `context`, `created_at`, `expires_at`.

### `approval_vote_cast`

Broadcast when a vote is cast on an approval gate via `POST /api/v1/approval-gates/{id}/vote`.

**Data:** Full `ApprovalGateResponse` object with updated `current_approvals`, `status`, and `resolved_at` fields. If enough approvals are reached, `status` changes to `approved`. A deny vote sets `status` to `denied`.

## Connection Limits

The `WebSocketManager` enforces a maximum of **100 concurrent connections** (configurable via the `max_connections` constructor parameter).

When the limit is reached, new connections are rejected:

| Condition | Close Code | Reason |
| --- | --- | --- |
| Connection limit reached | 4002 | `Too many connections` |

The limit is checked after authentication succeeds, so unauthenticated connections do not count against the limit.

## Error Codes

Summary of all WebSocket close codes used by the server:

| Code | Meaning | When |
| --- | --- | --- |
| 4001 | Unauthorized | Missing token or invalid token |
| 4002 | Too many connections | Server has reached `max_connections` (100) |
| 4003 | Auth not configured | `ARCHITECT_WS_TOKEN` env var is not set |

Standard WebSocket close codes (1000, 1001, 1006) may also occur during normal connection lifecycle and network interruptions.

## Client Implementation Notes

### Connecting

```typescript
const wsUrl = `ws://${host}:8016/api/v1/ws?token=${ARCHITECT_WS_TOKEN}`;
const ws = new WebSocket(wsUrl);

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  switch (message.type) {
    case 'escalation_created':
      // Handle new escalation
      break;
    case 'escalation_resolved':
      // Handle resolution
      break;
    case 'approval_gate_created':
      // Handle new gate
      break;
    case 'approval_vote_cast':
      // Handle vote
      break;
  }
};
```

### Reconnection Strategy

The server does not implement ping/pong keep-alive frames beyond the WebSocket protocol defaults. Clients should implement reconnection with exponential backoff:

1. On disconnect, wait 1 second before the first reconnection attempt.
2. Double the wait time on each subsequent failure, up to a maximum of 30 seconds.
3. Add random jitter (0-1 second) to avoid thundering herd when many clients reconnect simultaneously.
4. Reset the backoff timer after a successful connection that lasts longer than 10 seconds.

### Handling Disconnects

- **Close code 4001 or 4003:** Do not reconnect automatically. The token is invalid or not configured. Prompt the user to check credentials.
- **Close code 4002:** The server is at capacity. Reconnect with longer backoff (start at 5 seconds).
- **Close code 1006 (abnormal closure):** Network issue. Reconnect with standard backoff.
- **Close code 1000 or 1001 (normal closure):** Server shut down gracefully. Reconnect with standard backoff.

### Security Considerations

The authentication token is transmitted in the URL query string. This means it may appear in:

- Browser history
- Server access logs
- Proxy logs
- Referer headers (if the page navigates)

For production deployments, use WSS (TLS) to encrypt the connection and token in transit. Consider rotating the `ARCHITECT_WS_TOKEN` periodically.
