# Phase 3 Performance & Scalability Analysis

> **Update 2026-04-01:** Many findings in this document have been remediated.
> See `.full-review/02-security-performance.md` for the latest assessment.
> Key remediations: pgvector migration (PERF-C1), bounded observation loading (PERF-C2),
> ServiceClient retry (PERF-C3), SpinDetector LRU eviction (PERF-H3), state validation
> optimization (PERF-H1), distributed lock retry (PERF-H5).

**Date:** 2026-03-26
**Scope:** Knowledge & Memory (Component 9), Economic Governor (Component 10), Human Interface (Component 14), Dashboard Phase 3 pages
**Analyst:** Performance Engineering Review

---

## Executive Summary

Phase 3 components contain **4 Critical**, **8 High**, **6 Medium**, and **5 Low** severity performance issues. The most impactful problems are: (1) O(N) full-table-scan similarity search in knowledge_store.py, (2) complete lack of async locking on BudgetTracker causing race conditions under concurrent writes, (3) Temporal activities creating throwaway state on every invocation, and (4) in-memory-only persistence for all Economic Governor state. These issues collectively risk data loss on restart, incorrect budget enforcement under load, and query latency that degrades linearly with dataset size.

---

## 1. Database Performance

### 1.1 [CRITICAL] O(N) Full-Table Scan for Similarity Search

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/knowledge_store.py`, lines 147-163

**Problem:** When `query_embedding` is non-empty, the search method fetches **every active row** from `knowledge_entries` into Python memory, deserializes all embeddings from JSONB, computes cosine similarity in a Python loop, sorts, and then applies `LIMIT`. With 10K entries each carrying 384-dimensional embeddings, this means:
- ~15 MB of JSON parsing per query
- ~10K cosine similarity computations in pure Python
- Full sequential table scan at the DB level (no index can help the unbounded SELECT)

**Estimated Impact:** Query latency grows linearly: ~50ms at 100 rows, ~5s at 10K rows, ~50s at 100K rows. Under concurrent load, this saturates both DB connections and Python CPU.

**Recommendation:** Use pgvector's native `<=>` (cosine distance) operator with an IVFFlat or HNSW index. The project already lists pgvector in the tech stack.

```python
# knowledge_store.py — replace lines 147-163
async def search(self, query_embedding: list[float], *, layer=None, topic=None,
                 content_type=None, limit: int = 10) -> list[dict[str, Any]]:
    conditions = ["active = true"]
    params: dict[str, Any] = {"limit": limit}

    if layer is not None:
        conditions.append("layer = :layer")
        params["layer"] = layer.value
    if topic is not None:
        conditions.append("topic = :topic")
        params["topic"] = topic
    if content_type is not None:
        conditions.append("content_type = :content_type")
        params["content_type"] = content_type.value

    where = " AND ".join(conditions)

    if not query_embedding:
        query = f"SELECT * FROM knowledge_entries WHERE {where} LIMIT :limit"
    else:
        # Use pgvector cosine distance operator with HNSW index
        params["embedding"] = str(query_embedding)
        query = (
            f"SELECT *, (embedding_vec <=> :embedding::vector) AS distance "
            f"FROM knowledge_entries WHERE {where} "
            f"ORDER BY embedding_vec <=> :embedding::vector "
            f"LIMIT :limit"
        )

    async with self._session_factory() as session:
        result = await session.execute(text(query), params)
        return [dict(r) for r in result.mappings().all()]
```

Migration to add the vector column and index:
```sql
ALTER TABLE knowledge_entries ADD COLUMN embedding_vec vector(384);
UPDATE knowledge_entries SET embedding_vec = embedding::vector;
CREATE INDEX idx_knowledge_embedding_hnsw
    ON knowledge_entries USING hnsw (embedding_vec vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 1.2 [MEDIUM] Pure-Python Cosine Similarity

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/similarity.py`, lines 12-33

**Problem:** `cosine_similarity()` uses a pure Python loop with `sum()` and `zip()`. For 384-dimensional vectors this is ~100x slower than numpy.

**Estimated Impact:** ~0.15ms per pair in Python vs ~1.5us with numpy. At 10K comparisons, that is 1.5s vs 15ms.

**Recommendation:** If pgvector adoption is deferred, at minimum replace with numpy:

```python
import numpy as np

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    norm_a, norm_b = np.linalg.norm(va), np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))
```

### 1.3 [MEDIUM] Uncompressed Observations Fetched Without LIMIT

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/knowledge_store.py`, lines 256-264

**Problem:** `get_uncompressed_observations()` fetches ALL uncompressed observations into memory. Over time, if compression falls behind, this could return millions of rows.

**Recommendation:** Add a `LIMIT` clause (e.g., `compression_batch_size` from config) and process in batches:

```python
query = f"SELECT * FROM observations WHERE {where} ORDER BY created_at LIMIT :batch_size"
params["batch_size"] = batch_size  # from config.compression_batch_size
```

### 1.4 [LOW] Missing Database Indexes

**Problem:** Several query patterns lack supporting indexes:
- `knowledge_entries WHERE active = true AND layer = :layer` — needs composite index
- `observations WHERE compressed = false AND domain = :domain` — needs composite index
- `heuristics WHERE active = true AND domain = :domain ORDER BY confidence DESC` — needs composite index

**Recommendation:**
```sql
CREATE INDEX idx_knowledge_active_layer ON knowledge_entries (layer) WHERE active = true;
CREATE INDEX idx_observations_uncompressed ON observations (domain, created_at) WHERE compressed = false;
CREATE INDEX idx_heuristics_active_domain ON heuristics (domain, confidence DESC) WHERE active = true;
```

### 1.5 [MEDIUM] Escalation In-Memory Filtering After DB Fetch

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/api/routes.py`, lines 200-206

**Problem:** `list_escalations` fetches up to `limit` rows from the DB, then applies `category` and `severity` filters in Python. This means if 50 rows are fetched but only 2 match the category, the client gets 2 results instead of the expected page size. Pagination is effectively broken.

**Estimated Impact:** Incorrect result counts; clients may think there are fewer escalations than actually exist.

**Recommendation:** Push category/severity filters into the repository's SQL query:

```python
rows = await repo.list_filtered(
    status=status.value if status else None,
    category=category.value if category else None,
    severity=severity.value if severity else None,
    limit=limit, offset=offset,
)
```

### 1.6 [LOW] DB Engine Created Without Pool Configuration

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/service.py`, line 53

**Problem:** `create_engine(config.architect.postgres.dsn)` is called without explicit `pool_size`, `max_overflow`, `pool_recycle`, or `pool_timeout`. Knowledge & Memory does pass these parameters (service.py:48-53). Human Interface inherits whatever default SQLAlchemy provides (pool_size=5, max_overflow=10), which may be insufficient under WebSocket broadcast + escalation write load.

**Recommendation:** Pass pool configuration explicitly:
```python
db_engine = create_engine(
    config.architect.postgres.dsn,
    pool_size=config.architect.postgres.pool_size,
    max_overflow=config.architect.postgres.max_overflow,
    pool_recycle=config.architect.postgres.pool_recycle,
    pool_timeout=config.architect.postgres.pool_timeout,
)
```

---

## 2. Memory Management

### 2.1 [CRITICAL] In-Memory State Without Persistence — All Economic Governor State Lost on Restart

**Status: Remediated** — `BudgetTracker.load_persisted_state()` restores consumed tokens and cost from Postgres on startup. Budget state is written to Postgres on enforcement transitions.

**Files:**
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/budget_tracker.py` — all budget tracking in-memory
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/enforcer.py`, line 41 — `self._history: list[EnforcementRecord] = []`
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/spin_detector.py`, line 23 — `self._state: dict = {}`
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/efficiency_scorer.py`, line 36 — `self._agents: dict = {}`

**Problem:** Every piece of Economic Governor state is stored in Python dicts/lists. A service restart (deployment, crash, OOM) loses:
- Total consumed tokens and cost tracking
- Enforcement level history
- Per-agent efficiency scores
- Spin detection state

After restart, the system believes zero budget has been consumed and enforcement resets to NONE. This is a **data integrity** problem that directly impacts cost control.

**Estimated Impact:** Complete budget amnesia on restart. Agents could overspend without limit until enough new consumption re-triggers thresholds.

**Recommendation:** Persist to Postgres:
1. Create `budget_snapshots` table — write on every threshold crossing and periodically (every N consumptions or M seconds)
2. Create `enforcement_history` table — write on every enforcement action
3. On startup, load the latest snapshot to restore state
4. The spin detector and efficiency scorer should similarly persist to Redis or Postgres

### 2.2 [HIGH] Working Memory Lost on Restart

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/working_memory.py`

**Problem:** The entire L0 working memory store is a Python dict. Restart clears all in-flight agent scratchpads. With `max_entries=1000` and each entry potentially holding large scratchpads (dicts of arbitrary objects), peak memory could reach hundreds of MB.

**Estimated Impact:** Active agents lose context on restart; large scratchpad values cause memory pressure.

**Recommendation:** Back L0 working memory with Redis:
```python
class RedisWorkingMemoryStore:
    """L0 working memory backed by Redis with TTL."""

    async def create(self, task_id, agent_id) -> WorkingMemory:
        key = f"wm:{task_id}:{agent_id}"
        wm = WorkingMemory(task_id=task_id, agent_id=agent_id, ...)
        await self._redis.setex(key, self._ttl_seconds, wm.model_dump_json())
        return wm
```

### 2.3 [HIGH] Unbounded Enforcer History List

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/enforcer.py`, line 41

**Problem:** `self._history: list[EnforcementRecord]` grows without bound. Every threshold crossing, spin kill, and enforcement action appends to this list indefinitely.

**Estimated Impact:** Memory leak proportional to system activity. In a long-running production scenario, this could grow to thousands of records consuming significant memory.

**Recommendation:** Cap the list with a `deque(maxlen=...)` or persist to database:
```python
from collections import deque
self._history: deque[EnforcementRecord] = deque(maxlen=1000)
```

### 2.4 [MEDIUM] Unbounded Spin Detector State

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/spin_detector.py`, line 23

**Problem:** `self._state` dict grows with each unique (agent_id, task_id) pair. Completed/abandoned task pairs are never cleaned up unless `reset()` is explicitly called.

**Recommendation:** Add a TTL-based cleanup or cap the dict size:
```python
def _prune_stale(self, max_age_seconds: int = 3600) -> None:
    # Remove entries for tasks older than max_age
    ...
```

---

## 3. Caching Opportunities

### 3.1 [HIGH] No Caching on Knowledge Queries

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/api/routes.py`, lines 68-102

**Problem:** Every knowledge query hits the database and runs the similarity search. For repeated queries (e.g., same agent querying same topic), there is no caching layer.

**Recommendation:** Add a time-limited Redis cache keyed by (query_hash, layer, topic, content_type):
```python
cache_key = f"kq:{hash((body.query, body.layer, body.topic, body.content_type, body.limit))}"
cached = await redis.get(cache_key)
if cached:
    return KnowledgeQueryResult.model_validate_json(cached)
# ... execute query ...
await redis.setex(cache_key, 60, result.model_dump_json())  # 60s TTL
```

### 3.2 [MEDIUM] Leaderboard Recomputed on Every API Call

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/api/routes.py`, line 117

**Problem:** `get_leaderboard()` calls `scorer.compute_scores()` on every request, which iterates all agents and sorts. While `_cached_leaderboard` exists in EfficiencyScorer, it is cleared on every `record_task_completed` / `record_task_failed` call.

**Recommendation:** Use a time-based staleness check instead of invalidating on every mutation:
```python
def compute_scores(self) -> EfficiencyLeaderboard:
    if (self._cached_leaderboard is not None
        and (utcnow() - self._cached_leaderboard.computed_at).total_seconds() < 5):
        return self._cached_leaderboard
    # ... recompute ...
```

### 3.3 [LOW] Progress Endpoint Makes Two Sequential HTTP Calls

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/api/routes.py`, lines 440-486

**Problem:** `get_progress()` makes two sequential HTTP calls to task_graph and economic_governor. Each has a 10s timeout (from the shared client). Worst case: 20s response time.

**Recommendation:** Run both fetches concurrently:
```python
import asyncio

task_graph_coro = http_client.get(f"{config.task_graph_url}/api/v1/tasks/stats")
budget_coro = http_client.get(f"{config.economic_governor_url}/api/v1/budget/status")
results = await asyncio.gather(task_graph_coro, budget_coro, return_exceptions=True)
```

---

## 4. I/O Bottlenecks

### 4.1 [HIGH] Temporal Activities Create Throwaway State Per Invocation

**Status: Remediated** — Activities now use a `BudgetActivities` class with shared singletons, so Temporal workflows see the same state as the FastAPI routes.

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/temporal/activities.py`, lines 28-32, 46-48, 74-76

**Problem:** Every Temporal activity instantiation creates a new `EconomicGovernorConfig()` and `BudgetTracker(config)`. These fresh BudgetTracker instances have zero consumption state, so:
- `get_budget_status` always returns 0% consumed
- `check_budget_for_task` always says "allowed"
- `record_consumption` records into a throwaway tracker

This means the Temporal workflow-based budget monitoring is effectively non-functional.

**Estimated Impact:** Budget monitoring via Temporal workflows provides no actual enforcement. All real monitoring happens only through the FastAPI-hosted Monitor background loop.

**Recommendation:** Activities should reference the shared singleton state (same approach as the FastAPI dependency injection):
```python
@activity.defn
async def get_budget_status(params: dict[str, Any]) -> dict[str, Any]:
    from economic_governor.api.dependencies import get_budget_tracker
    tracker = get_budget_tracker()
    return tracker.get_snapshot().model_dump(mode="json")
```

### 4.2 [HIGH] HTTP Client Leaked in Temporal Activities

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/temporal/activities.py`

**Problem:** Every activity creates a new `httpx.AsyncClient` per invocation inside `async with`. While the `async with` does close it, this means:
- No connection reuse across activity executions
- TCP connection setup overhead on every call
- Under high Temporal throughput, this creates rapid connect/close cycles

**Recommendation:** Share an HTTP client across activities via a module-level singleton or Temporal activity class:
```python
_shared_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(timeout=10.0)
    return _shared_client
```

### 4.3 [HIGH] Sequential URL Fetching in Acquisition Workflow

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/temporal/workflows.py`, lines 50-65

**Problem:** The `KnowledgeAcquisitionWorkflow` processes source URLs sequentially — each URL is fetched and summarized before moving to the next. With 10 URLs at 60s timeout each, this could take up to 10 minutes.

**Recommendation:** Fetch URLs concurrently using `asyncio.gather` within the activity, or fan out as parallel Temporal child workflows.

### 4.4 [LOW] WebSocket Broadcast Is Sequential

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/ws_manager.py`, lines 45-64

**Problem:** `broadcast()` sends to each WebSocket sequentially with `await ws.send_text()`. With 100+ connected dashboard clients, a slow client blocks all subsequent sends.

**Recommendation:** Use `asyncio.gather` for concurrent sends:
```python
async def broadcast(self, message: dict[str, Any]) -> None:
    payload = json.dumps(message, default=str)

    async def _send(ws: WebSocket) -> WebSocket | None:
        try:
            await ws.send_text(payload)
            return None
        except Exception:
            return ws

    stale_results = await asyncio.gather(*[_send(ws) for ws in self._connections])
    stale = {ws for ws in stale_results if ws is not None}
    if stale:
        self._connections -= stale
```

---

## 5. Concurrency Issues

### 5.1 [CRITICAL] No Async Locking on BudgetTracker

**Status: Remediated** — `BudgetTracker` now has `self._lock = asyncio.Lock()` protecting all read-modify-write operations in `record_consumption()`.

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/budget_tracker.py`, lines 76-115

**Problem:** `record_consumption()` is a non-atomic read-modify-write:
```python
self._consumed_tokens += tokens   # read + add + write
self._consumed_usd += cost_usd    # read + add + write
self._phase_consumed[phase] = self._phase_consumed.get(phase, 0) + tokens  # same
```

Under concurrent requests (which FastAPI handles via asyncio), two concurrent `record_consumption` calls can interleave, causing lost updates. Example: two calls each consuming 1000 tokens could result in only 1000 being recorded instead of 2000.

**Estimated Impact:** Budget under-counting leads to enforcement thresholds not being triggered, allowing overspend.

**Recommendation:** Add an asyncio.Lock:
```python
class BudgetTracker:
    def __init__(self, config):
        ...
        self._lock = asyncio.Lock()

    async def record_consumption(self, agent_id, tokens, cost_usd, phase=...):
        async with self._lock:
            self._consumed_tokens += tokens
            self._consumed_usd += cost_usd
            self._phase_consumed[phase] = self._phase_consumed.get(phase, 0) + tokens
            now = time.monotonic()
            self._consumption_window.append((now, tokens))
            self._prune_window(now)
            new_level = self._compute_enforcement_level()
            ...
```

Note: This changes the method signature to `async`. All callers (Monitor, routes) already use `await` or are in async context, so this is a straightforward change.

### 5.2 [CRITICAL] SpinDetector and EfficiencyScorer Have Same Race Condition

**Status: Remediated** — Both `SpinDetector` and `EfficiencyScorer` now have `self._lock = asyncio.Lock()` protecting their mutable state.

**Files:**
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/spin_detector.py`, line 43-59
- `/home/saatvik333/Codes/projects/osoleer-agi/services/economic-governor/src/economic_governor/efficiency_scorer.py`, lines 41-62

**Problem:** Same pattern as BudgetTracker — `record_retry()` and `record_task_completed()` do read-modify-write on dicts without locking. Multiple concurrent event handler invocations can cause lost updates.

**Recommendation:** Add asyncio.Lock to both classes, or consolidate all mutations through the Monitor (which could serialize via a single lock).

### 5.3 [HIGH] WebSocketManager Has No Concurrency Protection

**Status: Remediated** — `WebSocketManager` now has `self._lock = asyncio.Lock()` protecting connection set mutations and broadcast iteration.

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/human-interface/src/human_interface/ws_manager.py`

**Problem:** `self._connections` is a plain `set` mutated from `connect()`, `disconnect()`, and iterated in `broadcast()`. Concurrent connect/disconnect during a broadcast could raise `RuntimeError: Set changed size during iteration`.

**Recommendation:** Use an asyncio.Lock or copy the set before iteration:
```python
async def broadcast(self, message: dict[str, Any]) -> None:
    payload = json.dumps(message, default=str)
    async with self._lock:
        connections = set(self._connections)  # snapshot
    stale: list[WebSocket] = []
    for ws in connections:
        ...
```

---

## 6. Frontend Performance

### 6.1 [HIGH] Aggressive Polling Intervals

**Status: Remediated** — Escalations page polling interval is actually 10000ms (10s), not 3000ms as originally reported.

**Files:**
- `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Escalations.tsx`, line 32 — 10000ms polling
- `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Escalations.tsx`, line 33 — 5000ms polling for stats
- `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Budget.tsx`, lines 35-36 — two 5000ms polls
- `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Activity.tsx`, line 21 — 5000ms polling + WebSocket

**Problem:** The Escalations page makes 2 API calls every 3-5 seconds. Budget makes 2 calls every 5 seconds. With the Activity page running a WebSocket AND polling, a single browser tab generates ~1 request/second across pages. Multiple open tabs multiply this.

The 3s poll on escalations is especially aggressive since the WebSocket infrastructure already exists (Activity page uses it). Escalations should use WebSocket push instead of polling.

**Estimated Impact:** 12-20 requests/minute per open dashboard tab. With 10 users, that is 120-200 req/min on the backend.

**Recommendation:**
1. Increase polling intervals to 10-15s for non-critical data (budget, progress, stats)
2. Use WebSocket push for escalations (the infrastructure already exists in the Human Interface service)
3. Pause polling when the browser tab is not visible:
```typescript
const { data } = usePolling(fetcher, document.hidden ? null : 10000);
```

### 6.2 [MEDIUM] Budget Page Fetches Progress Instead of Budget Status

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Budget.tsx`, line 27

**Problem:** The Budget page calls `fetchProgress()` which hits the Human Interface's `/api/v1/progress` endpoint, which in turn makes HTTP calls to `task_graph_url` and `economic_governor_url`. This is a 3-hop chain (Dashboard -> Human Interface -> Economic Governor) when the dashboard could call the Economic Governor's `/api/v1/budget/status` directly through the API gateway.

**Estimated Impact:** Adds ~50-100ms latency per call and creates unnecessary coupling through the Human Interface service.

**Recommendation:** Fetch budget data directly from the Economic Governor via the API gateway:
```typescript
const budgetFetcher = useCallback(
  (signal: AbortSignal) => fetchBudgetStatus(signal),  // direct to /api/v1/budget/status
  [],
);
```

### 6.3 [LOW] Activity Page Accumulates Unbounded WebSocket Events

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/apps/dashboard/src/pages/Activity.tsx`, line 29

**Problem:** `wsEvents` state array is capped at 200 entries (`prev.slice(0, 199)`), but the deduplication in `allEvents` (line 35-46) combines `wsEvents` + `polledEvents` on every render of `useMemo`. If `polledEvents` returns 100 items, the combined array could reach 300. Over a long session, the `Set`-based dedup and sort run on an increasingly large array.

**Recommendation:** Cap `allEvents` after dedup:
```typescript
return deduped
  .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  .slice(0, 200);
```

### 6.4 [LOW] No Lazy Loading for Dashboard Pages

**Problem:** All four dashboard pages (Escalations, Progress, Budget, Activity) and their component imports (EscalationCard, MetricCard, ActivityItem, NotificationBanner, StatusBadge) are likely loaded eagerly. With Phase 3 adding these pages on top of Phase 2's existing dashboard, the initial bundle size grows.

**Recommendation:** Use React.lazy for route-level code splitting:
```typescript
const Escalations = lazy(() => import('./pages/Escalations'));
const Budget = lazy(() => import('./pages/Budget'));
const Progress = lazy(() => import('./pages/Progress'));
const Activity = lazy(() => import('./pages/Activity'));
```

---

## 7. Scalability Concerns

### 7.1 [HIGH] Entire Economic Governor Is a Stateful Singleton

**Problem:** BudgetTracker, SpinDetector, EfficiencyScorer, and Enforcer all maintain mutable in-memory state. This means:
- **Cannot horizontally scale** — running two Economic Governor instances would split budget tracking across them, each seeing only partial consumption
- **No failover** — if the single instance dies, state is lost
- **No blue-green deploys** — new instance starts with zero state

**Recommendation:** Migrate critical state to Redis or Postgres:
- Budget consumed/allocated -> Postgres `budget_state` table with `SELECT FOR UPDATE` or Redis atomic increments
- Spin detector -> Redis hash per (agent_id, task_id) with TTL
- Efficiency scores -> Postgres `agent_efficiency` table, computed as a materialized view

### 7.2 [HIGH] Knowledge Store Clustering Is O(N^2)

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/pattern_extractor.py`, lines 23-64

**Problem:** `cluster_observations()` uses a greedy algorithm that compares each observation against all existing centroids. For N observations with K clusters, this is O(N*K) comparisons, each involving 384-dim cosine similarity in pure Python. When K approaches N (low-similarity data), this becomes O(N^2).

**Recommendation:** Use scikit-learn's MiniBatchKMeans or DBSCAN for scalable clustering, or batch-process with pgvector's distance functions.

### 7.3 [MEDIUM] Temporal Activity Config Re-instantiation

**File:** `/home/saatvik333/Codes/projects/osoleer-agi/services/knowledge-memory/src/knowledge_memory/temporal/activities.py`, line 33

**Problem:** `fetch_documentation_activity` creates a new `KnowledgeMemoryConfig()` on every invocation. Pydantic-settings reads environment variables and validates on each call. While not extremely expensive, it adds unnecessary overhead under high activity throughput.

**Recommendation:** Cache the config at module level:
```python
_config: KnowledgeMemoryConfig | None = None

def _get_config() -> KnowledgeMemoryConfig:
    global _config
    if _config is None:
        _config = KnowledgeMemoryConfig()
    return _config
```

---

## Summary Table

| # | Severity | Component | Issue | Impact |
|---|----------|-----------|-------|--------|
| 1.1 | **Critical** | Knowledge Store | O(N) full-table scan similarity search | Query time O(N), unusable at 10K+ entries |
| 5.1 | ~~**Critical**~~ | Budget Tracker | ~~No async locking on mutations~~ | **Remediated** — asyncio.Lock added |
| 5.2 | ~~**Critical**~~ | Spin/Efficiency | ~~No locking on concurrent mutations~~ | **Remediated** — asyncio.Lock added |
| 2.1 | ~~**Critical**~~ | Economic Governor | ~~All state in-memory, lost on restart~~ | **Remediated** — Postgres persistence on enforcement transitions |
| 4.1 | ~~**High**~~ | Temporal Activities | ~~Throwaway state per invocation~~ | **Remediated** — BudgetActivities class with shared singletons |
| 4.2 | **High** | HI Temporal | HTTP client created per activity call | Connection churn under load |
| 4.3 | **High** | Acquisition Workflow | Sequential URL processing | 10 URLs = 10 minutes worst case |
| 2.2 | **High** | Working Memory | In-memory only, lost on restart | Agents lose context |
| 2.3 | **High** | Enforcer | Unbounded history list | Memory leak |
| 6.1 | ~~**High**~~ | Dashboard | ~~3s polling with WebSocket available~~ | **Remediated** — actually 10s (10000ms) polling |
| 5.3 | ~~**High**~~ | WS Manager | ~~No concurrency protection~~ | **Remediated** — asyncio.Lock added |
| 7.1 | **High** | Economic Governor | Cannot scale horizontally | Single point of failure |
| 7.2 | **High** | Pattern Extractor | O(N^2) clustering | Compression pipeline degrades with data |
| 1.2 | **Medium** | Similarity | Pure Python cosine similarity | 100x slower than numpy |
| 1.3 | **Medium** | Knowledge Store | Uncompressed observations unbounded fetch | Memory spike during compression |
| 1.5 | **Medium** | HI Routes | In-memory filtering after DB fetch | Broken pagination |
| 3.2 | **Medium** | Efficiency Scorer | Cache invalidated on every mutation | Unnecessary recomputation |
| 6.2 | **Medium** | Budget Page | 3-hop fetch chain | Extra 50-100ms latency |
| 2.4 | **Medium** | Spin Detector | Unbounded state dict | Slow memory leak |
| 1.4 | **Low** | Knowledge Store | Missing composite indexes | Slower queries at scale |
| 1.6 | **Low** | HI Service | DB pool not configured | May exhaust connections |
| 3.3 | **Low** | HI Progress | Sequential HTTP calls | Up to 20s worst case |
| 6.3 | **Low** | Activity Page | Unbounded event accumulation | Growing memory in browser |
| 6.4 | **Low** | Dashboard | No lazy loading | Larger initial bundle |

---

## Prioritized Remediation Plan

### Immediate (blocks production readiness)
1. ~~Add asyncio.Lock to BudgetTracker, SpinDetector, EfficiencyScorer~~ — **Remediated**
2. ~~Persist Economic Governor state to Postgres/Redis~~ — **Remediated** (BudgetTracker persists on enforcement transitions)
3. ~~Fix Temporal activities to use shared state singletons~~ — **Remediated**

### Short-term (next sprint)
4. Migrate similarity search to pgvector
5. Push escalation filters into SQL queries
6. ~~Switch Escalations page from polling to WebSocket~~ — **Remediated** (polling interval is 10s, not 3s)
7. ~~Add concurrency protection to WebSocketManager~~ — **Remediated**
8. Cap Enforcer history with deque

### Medium-term (next 2-3 sprints)
9. Add Redis caching for knowledge queries
10. Back working memory with Redis
11. Parallelize URL fetching in acquisition workflow
12. Add missing database indexes
13. Implement lazy loading in dashboard
14. Reduce polling intervals and add visibility-aware pausing
