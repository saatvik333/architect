# ADR-003: Event Sourcing with PostgreSQL and Redis Streams

**Status:** Accepted

**Date:** 2025-01-15

---

## Context

ARCHITECT's design principles state that "agents are disposable, state is sacred" and that every state change must be auditable and replayable. The system needs to:

1. **Record every state mutation** as an immutable event so that the full history of the system can be reconstructed at any point in time.
2. **Decouple producers from consumers:** When the Task Graph Engine completes a task, the World State Ledger, Knowledge Memory, and Human Interface all need to react -- but the Task Graph Engine should not know about or depend on any of them.
3. **Support real-time streaming:** Components like the Evaluation Engine and Coding Agent need to react to events within milliseconds, not on a polling interval.
4. **Enable replay:** If a new service is added (e.g., the Failure Taxonomy in Phase 4), it should be able to replay historical events to build its initial state.
5. **Guarantee at-least-once delivery** so that no event is silently dropped.

The system publishes a variety of event types across the lifecycle: `task.created`, `task.started`, `task.completed`, `task.failed`, `proposal.created`, `proposal.accepted`, `proposal.rejected`, `agent.spawned`, `agent.completed`, `eval.completed`, `ledger.updated`, and `budget.warning`.

## Decision

We adopt a **dual-storage event sourcing architecture**:

1. **PostgreSQL append-only event log** serves as the durable, authoritative event store. Every event is written to the `event_log` table with an `idempotency_key` (using `ON CONFLICT DO NOTHING`) to prevent duplicate writes. Events carry a type, timestamp, correlation ID, and JSON payload. This log supports historical replay and point-in-time reconstruction.

2. **Redis Streams** serve as the real-time pub/sub transport. After an event is persisted to PostgreSQL, it is published to a Redis Stream named `architect:{event_type}` (e.g., `architect:task.completed`). Consumers use Redis consumer groups for load-balanced, at-least-once delivery.

All events are wrapped in an **`EventEnvelope`** -- a frozen Pydantic model containing:
- `id`: Unique event ID (UUID)
- `type`: Event type from the `EventType` enum
- `timestamp`: UTC timestamp
- `correlation_id`: Optional ID linking related events across a workflow
- `payload`: Typed event data (serialized as a dict)

The `EventPublisher` class in `architect-events` manages the Redis connection and publishes serialized envelopes to the appropriate stream via `XADD`. Each event type has a corresponding typed schema (`TaskCreatedEvent`, `ProposalAcceptedEvent`, `EvalCompletedEvent`, etc.) that is serialized into the envelope payload.

### Alternatives considered

1. **Apache Kafka:** The industry standard for event streaming at scale. However, Kafka requires a JVM-based broker cluster (ZooKeeper or KRaft), significantly increasing infrastructure complexity. ARCHITECT's event volume (hundreds to low thousands of events per hour in Phase 1) does not justify Kafka's operational overhead. Kafka's partition-based ordering model is more complex to reason about than Redis Streams' per-stream ordering.

2. **NATS JetStream:** Already present in the infrastructure stack for inter-agent messaging (Phase 2). JetStream provides durable streams with replay. However, using NATS for both the event bus and the agent comm bus would conflate two different communication patterns (event sourcing vs. request-reply messaging) in a single system. Redis is already required for state caching, so using Redis Streams for events avoids adding another durable storage dependency for this concern.

3. **Pure PostgreSQL LISTEN/NOTIFY:** PostgreSQL's built-in pub/sub mechanism. Simple to set up with no additional infrastructure. However, LISTEN/NOTIFY is fire-and-forget with no delivery guarantees -- if a consumer is disconnected when a NOTIFY is sent, the event is lost. No consumer groups, no replay, no backpressure. Unsuitable for a system where event delivery reliability is a core requirement.

## Consequences

### Positive

- **Complete audit trail:** Every state change in the system is recorded as an immutable event in PostgreSQL. The `idempotency_key` ensures that retries and replays do not produce duplicate records.
- **Lightweight real-time pub/sub:** Redis Streams provide millisecond-latency event delivery without the operational burden of a dedicated message broker. Since Redis is already in the stack for caching, there is no additional infrastructure to manage.
- **Consumer groups:** Redis Streams' consumer group feature allows multiple instances of a service to load-balance event processing, with automatic tracking of which messages each consumer has acknowledged. This supports horizontal scaling of event consumers.
- **At-least-once delivery:** Between PostgreSQL's durable writes and Redis Streams' consumer group acknowledgment tracking, events are guaranteed to be delivered at least once. Consumers must be idempotent, which aligns with the proposal-gated mutation model (proposals carry idempotency keys).
- **Replay capability:** New services can replay the PostgreSQL event log to reconstruct historical state. Redis Streams also retain events up to a configurable limit, supporting short-term replay without hitting the database.
- **Correlation tracking:** The `correlation_id` field in `EventEnvelope` links all events produced during a single workflow execution, enabling end-to-end tracing of a task from creation through evaluation to ledger commit.

### Negative

- **Dual-write consistency:** Writing to both PostgreSQL and Redis introduces a window where the database write succeeds but the Redis publish fails (or vice versa). This is mitigated by writing to PostgreSQL first (the authoritative store) and treating Redis publication as best-effort with a retry. In the worst case, a consumer can fall back to polling the PostgreSQL event log.
- **Redis persistence limitations:** While Redis with AOF (`appendonly yes`) provides reasonable durability, it is not as durable as PostgreSQL. A Redis crash between AOF syncs could lose recent events. This is acceptable because PostgreSQL is the authoritative store and Redis is the delivery mechanism.
- **Schema evolution:** Event payloads are serialized as JSON dicts. Adding or removing fields from event schemas requires careful versioning to avoid breaking consumers that expect a specific payload shape. The typed event schemas (e.g., `TaskCompletedEvent`) help, but old events in the log will have the old schema.
- **No exactly-once delivery:** Redis Streams provide at-least-once, not exactly-once delivery. All consumers must handle duplicate events idempotently. This is an inherent trade-off of the chosen architecture.
