# ADR-006: Phase 3 Design Decisions

**Status:** Accepted

**Date:** 2026-03-26

---

## Context

Phase 3 introduces three new components: Knowledge & Memory (Component 9), Economic Governor (Component 10), and Human Interface (Component 14). Each component required significant architectural decisions around data storage, communication patterns, and state management. This ADR captures the four most consequential decisions and their trade-offs.

---

## Decision 1: 5-Layer Memory Hierarchy (Knowledge & Memory)

### Context

Agents need access to knowledge at different scopes and lifetimes: ephemeral task-scoped scratchpads, persistent project knowledge, reusable code patterns, synthesized heuristics, and cross-domain meta-strategies. A flat storage model would not distinguish between volatile working data and permanent learned knowledge.

### Decision

Implement a 5-layer memory hierarchy:

- **L0 Working** -- In-process Python dict, task-scoped, TTL-evicted. Not persisted.
- **L1 Project** -- Postgres + pgvector, project lifetime, stores knowledge entries with embeddings.
- **L2 Patterns** -- Reusable code patterns extracted from observations via LLM. Permanent.
- **L3 Heuristics** -- "When X, do Y" rules synthesized from pattern clusters. Permanent.
- **L4 Meta-Strategy** -- Cross-domain orchestration improvements. Permanent.

L0 is in-process because working memory is high-frequency, low-durability data. Persisting every scratchpad write to Redis or Postgres would add latency to the agent's inner loop for data that is discarded at task completion. L1 through L4 are stored in Postgres because they represent durable knowledge that must survive restarts and be queryable via SQL and vector similarity.

### Consequences

- L0 data is lost on service restart. Active agents lose their scratchpad context. This is acceptable for the current single-instance deployment model but would need Redis backing for horizontal scaling.
- The compression pipeline (observations -> patterns -> heuristics -> meta-strategies) runs as a Temporal workflow, decoupled from real-time queries.
- Embedding-based similarity search at L1 uses pgvector with HNSW indexes. Initial implementation used pure Python cosine similarity (O(N) full-table scan); this has been partially migrated to pgvector native queries.

---

## Decision 2: In-Memory Budget Tracking with Periodic DB Snapshots (Economic Governor)

### Context

The Economic Governor tracks token consumption and cost across all agents in real time. Budget state (consumed tokens, consumed USD, phase breakdown) must be updated on every LLM call and queried on every routing decision. Persisting every update to Postgres would add latency to the critical path.

### Decision

Maintain budget state in Python memory (BudgetTracker singleton) with periodic snapshots to Postgres on enforcement level transitions. On startup, load the latest snapshot to restore state. An asyncio.Lock protects all read-modify-write operations to prevent race conditions under concurrent FastAPI requests.

The SpinDetector and EfficiencyScorer follow the same pattern: in-memory state with LRU eviction (SpinDetector caps entries to prevent unbounded growth).

### Consequences

- Consumption recorded between persistence points is lost on crash. The window of data loss is bounded by the monitoring poll interval (default 10 seconds) plus the time since the last enforcement transition.
- The Economic Governor cannot be horizontally scaled as-is. Two instances would each track partial consumption. Migration to Redis atomic increments or Postgres `SELECT FOR UPDATE` would be needed for multi-instance deployments.
- The asyncio.Lock serializes budget mutations within a single process, preventing under-counting that would cause missed enforcement thresholds.

---

## Decision 3: WebSocket for Dashboard Notifications (Human Interface)

### Context

The dashboard needs to display real-time escalation notifications, approval events, and progress updates. Two viable options: Server-Sent Events (SSE) or WebSocket.

### Decision

Use WebSocket for the Human Interface to dashboard connection.

Rationale:
- **Bidirectional**: Escalation responses (approve/reject) flow from dashboard to server. SSE is server-to-client only; bidirectional use would require a separate POST endpoint for each action, complicating the interaction model.
- **Multiplexed message types**: A single WebSocket connection carries escalation_created, escalation_resolved, approval_gate_created, approval_vote_cast, event, progress.update, and ping messages. SSE would need multiple EventSource connections or a single stream with client-side demuxing.
- **Connection lifecycle**: WebSocket connections are authenticated via `ARCHITECT_WS_TOKEN` on connect. The `WebSocketManager` tracks active connections with an asyncio.Lock to prevent set-mutation races during broadcast.

### Consequences

- WebSocket requires explicit connection management (connect, disconnect, reconnect on failure). The dashboard implements polling fallback (5-10 second intervals) for reliability when WebSocket is unavailable.
- Token validation is presence-only (any non-empty token is accepted). This is a known limitation documented in the Phase 3 design doc; full token verification against an auth backend is deferred.
- The API Gateway must proxy WebSocket connections, which adds configuration complexity compared to SSE (which works over standard HTTP).

---

## Decision 4: Raw SQL for pgvector Queries (Knowledge Store)

### Context

The Knowledge Store needs to perform vector similarity search against the `knowledge_entries` table using pgvector's `<=>` (cosine distance) operator with HNSW indexes. SQLAlchemy's ORM layer does not natively support pgvector operators or the `vector` column type.

### Decision

Use raw SQL via `sqlalchemy.text()` for knowledge queries that involve vector similarity, while using standard ORM patterns for non-vector CRUD operations.

### Consequences

- Raw SQL queries bypass SQLAlchemy's type checking and query composition. Filter conditions are built via string concatenation with parameterized values (`:param` style), which is safe against injection but harder to maintain than ORM query builders.
- The initial implementation computed cosine similarity in pure Python (O(N) full-table scan). This has been partially migrated to pgvector native queries using the `<=>` operator with HNSW indexes, reducing query time from O(N) to O(log N).
- A full migration to a pgvector-aware SQLAlchemy extension (e.g., `pgvector-python`'s SQLAlchemy integration) would allow ORM-level vector queries but is deferred to avoid adding another dependency.
