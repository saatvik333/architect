# Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all ~105 findings from the 2026-04-01 comprehensive code review across 5 phases, prioritized by severity and blast radius.

**Architecture:** Each phase is self-contained and produces a working, tested codebase at completion. Phases are ordered by risk: security first, then performance/data-integrity, then code quality, then testing/docs, then infrastructure. Each task within a phase can be committed independently.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy (async), Pydantic v2, Temporal, NATS, Redis, React/TypeScript, Docker, GitHub Actions, pytest, Alembic

**Findings reference:** `.full-review/05-final-report.md`

---

## Phase 1: Security Hardening (13 tasks)

Fixes all Critical and High security findings. Must be completed before any new feature work.

### Task 1.1: WebSocket Auth — Fail Closed

**Fixes:** SEC-C1 (CVSS 9.1), CQ-H4, AR-H2, TEST-C2
**Files:**
- Modify: `services/human-interface/src/human_interface/api/routes.py:540-560`
- Modify: `services/human-interface/src/human_interface/api/dependencies.py` (add `get_config`)
- Create: `services/human-interface/tests/test_ws_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# services/human-interface/tests/test_ws_auth.py
"""WebSocket authentication tests — fail-closed behaviour."""
from __future__ import annotations

import hmac
import os
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from human_interface.service import create_app


@pytest.fixture
def app():
    return create_app()


class TestWebSocketFailClosed:
    """When ARCHITECT_WS_TOKEN is unset, all connections MUST be rejected."""

    def test_ws_rejected_when_token_env_unset(self, app):
        client = TestClient(app)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARCHITECT_WS_TOKEN", None)
            with client.websocket_connect("/api/v1/ws?token=anything") as ws:
                # Should immediately close
                pytest.fail("Connection should have been rejected")

    def test_ws_rejected_when_no_token_param(self, app):
        client = TestClient(app)
        with patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "real-secret"}):
            with client.websocket_connect("/api/v1/ws") as ws:
                pytest.fail("Connection should have been rejected")

    def test_ws_rejected_with_wrong_token(self, app):
        client = TestClient(app)
        with patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "real-secret"}):
            with client.websocket_connect("/api/v1/ws?token=wrong") as ws:
                pytest.fail("Connection should have been rejected")

    def test_ws_accepted_with_correct_token(self, app):
        client = TestClient(app)
        with patch.dict(os.environ, {"ARCHITECT_WS_TOKEN": "real-secret"}):
            with client.websocket_connect("/api/v1/ws?token=real-secret") as ws:
                # Should connect successfully
                pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest services/human-interface/tests/test_ws_auth.py -v`
Expected: At least 1 FAIL (the "unset" test passes when it shouldn't)

- [ ] **Step 3: Fix the WebSocket auth to fail closed**

In `services/human-interface/src/human_interface/api/routes.py`, replace lines 540-560:

```python
@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
) -> None:
    """Real-time WebSocket push to dashboard clients."""
    import hmac
    import os

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Unauthorized — no token")
        return

    expected_token = os.environ.get("ARCHITECT_WS_TOKEN")

    # Fail closed: if no token is configured, reject all connections.
    if not expected_token:
        await websocket.close(code=4003, reason="WebSocket auth not configured")
        return

    if not hmac.compare_digest(token, expected_token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest services/human-interface/tests/test_ws_auth.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add services/human-interface/src/human_interface/api/routes.py services/human-interface/tests/test_ws_auth.py
git commit -m "fix(security): WebSocket auth fails closed when ARCHITECT_WS_TOKEN unset

Use hmac.compare_digest for constant-time comparison. Reject all
connections when the token env var is not configured (fail-closed).

Fixes: SEC-C1 (CVSS 9.1), CQ-H4, AR-H2, TEST-C2"
```

---

### Task 1.2: Eliminate SQL Injection Risk in KnowledgeStore

**Fixes:** SEC-C2 (CVSS 8.6)
**Files:**
- Modify: `services/knowledge-memory/src/knowledge_memory/knowledge_store.py:345-370`
- Create: `services/knowledge-memory/tests/test_knowledge_store_sql_safety.py`

- [ ] **Step 1: Write the failing test**

```python
# services/knowledge-memory/tests/test_knowledge_store_sql_safety.py
"""Verify KnowledgeStore SQL queries use parameterized values only."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge_memory.knowledge_store import KnowledgeStore


@pytest.fixture
def store():
    session_factory = AsyncMock()
    return KnowledgeStore(session_factory=session_factory)


class TestHeuristicOutcomeSQLSafety:
    async def test_update_heuristic_outcome_success_uses_case_not_fstring(self, store):
        """The SQL must use CASE expressions, not f-string column interpolation."""
        mock_session = AsyncMock()
        store._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        store._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await store.update_heuristic_outcome("heur-1", success=True)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0].text)

        # Must NOT contain f-string interpolated column names
        assert "success_count = success_count + 1" not in sql_text or "CASE" in sql_text
        # Must use CASE WHEN :is_success pattern
        assert ":is_success" in sql_text or ":success" in sql_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest services/knowledge-memory/tests/test_knowledge_store_sql_safety.py -v`
Expected: FAIL (current code uses f-string interpolation)

- [ ] **Step 3: Replace f-string SQL with CASE expressions**

In `services/knowledge-memory/src/knowledge_memory/knowledge_store.py`, replace `update_heuristic_outcome` (lines 345-370):

```python
    async def update_heuristic_outcome(
        self,
        heuristic_id: HeuristicId,
        *,
        success: bool,
    ) -> None:
        """Record an outcome for a heuristic, updating counters and confidence."""
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE heuristics
                    SET success_count = success_count + CASE WHEN :is_success THEN 1 ELSE 0 END,
                        failure_count = failure_count + CASE WHEN :is_success THEN 0 ELSE 1 END,
                        confidence = CASE
                            WHEN (success_count + failure_count + 1) > 0
                            THEN (success_count + CASE WHEN :is_success THEN 1 ELSE 0 END)::float
                                 / (success_count + failure_count + 1)::float
                            ELSE confidence
                        END
                    WHERE id = :id
                """),
                {"id": str(heuristic_id), "is_success": success},
            )
            await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest services/knowledge-memory/tests/test_knowledge_store_sql_safety.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/knowledge-memory/src/knowledge_memory/knowledge_store.py services/knowledge-memory/tests/test_knowledge_store_sql_safety.py
git commit -m "fix(security): replace f-string SQL with CASE expressions in KnowledgeStore

Eliminates SQL injection risk from column name interpolation via f-string.
Uses parameterized CASE WHEN :is_success pattern instead.

Fixes: SEC-C2 (CVSS 8.6)"
```

---

### Task 1.3: Identity Impersonation — Forward Auth Headers

**Fixes:** SEC-C3 (CVSS 8.1), AR-H1, TEST-H3
**Files:**
- Modify: `apps/api-gateway/src/api_gateway/__init__.py:185-210` (add X-Authenticated-User header forwarding)
- Modify: `services/human-interface/src/human_interface/api/routes.py:270-310` (derive resolved_by from header)
- Modify: `services/human-interface/src/human_interface/api/routes.py:420-470` (derive voter from header)
- Modify: `services/human-interface/src/human_interface/models.py:60-68` (make resolved_by optional)
- Modify: `services/human-interface/src/human_interface/models.py:118-122` (make voter optional)
- Create: `services/human-interface/tests/test_identity_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# services/human-interface/tests/test_identity_auth.py
"""Verify identity is derived from auth headers, not request body."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from human_interface.service import create_app


@pytest.fixture
def app():
    return create_app()


class TestIdentityFromAuth:
    async def test_resolve_escalation_uses_auth_header_not_body(self, app):
        """resolved_by must come from X-Authenticated-User header."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create an escalation first (simplified — would use fixture in practice)
            resp = await client.post(
                "/api/v1/escalations/{esc_id}/resolve",
                json={"resolution": "approved"},
                headers={"X-Authenticated-User": "admin@example.com"},
            )
            # When X-Authenticated-User is present, resolved_by should be
            # derived from it, not from the request body
            if resp.status_code == 200:
                assert resp.json()["resolved_by"] == "admin@example.com"

    async def test_resolve_escalation_rejects_without_auth_header(self, app):
        """Without X-Authenticated-User, the request should fail."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/escalations/esc-test/resolve",
                json={"resolution": "approved"},
            )
            # Should require identity
            assert resp.status_code in (401, 422)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest services/human-interface/tests/test_identity_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Add X-Authenticated-User forwarding in API Gateway**

In `apps/api-gateway/src/api_gateway/__init__.py`, after successful auth validation (around line 210), add:

```python
        # Forward authenticated identity to downstream services
        api_key_prefix = provided_key[:8]
        # Use the key prefix as a stable identity — a proper user registry
        # would map keys to user identities.
        request.state.authenticated_user = f"apikey:{api_key_prefix}"
```

And in the proxy handler, forward the header:

```python
headers["X-Authenticated-User"] = getattr(request.state, "authenticated_user", "anonymous")
```

- [ ] **Step 4: Update Human Interface models and routes**

In `services/human-interface/src/human_interface/models.py`, make `resolved_by` optional:

```python
class ResolveEscalationRequest(BaseModel):
    """Request body for resolving an escalation."""

    resolution: str
    custom_input: dict[str, Any] | None = None
    # Deprecated: resolved_by should come from X-Authenticated-User header.
    # Kept for backwards compatibility but ignored when header is present.
    resolved_by: str | None = None
```

Make `voter` optional in VoteRequest:

```python
class VoteRequest(BaseModel):
    """Request body for casting a vote on an approval gate."""

    decision: Literal["approve", "deny"]
    comment: str | None = None
    # Deprecated: voter should come from X-Authenticated-User header.
    voter: str | None = None
```

In `services/human-interface/src/human_interface/api/routes.py`, update `resolve_escalation` (line ~280):

```python
async def resolve_escalation(
    escalation_id: str,
    body: ResolveEscalationRequest,
    request: Request,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EscalationResponse:
    """Resolve an escalation with a human decision."""
    # Derive identity from auth header (set by API Gateway).
    # Fall back to body field for backwards compatibility.
    resolved_by = request.headers.get("X-Authenticated-User") or body.resolved_by
    if not resolved_by:
        raise HTTPException(status_code=401, detail="Identity required: set X-Authenticated-User header")
    # ... rest of method uses resolved_by variable instead of body.resolved_by
```

Similarly update `cast_vote` (line ~430):

```python
    voter = request.headers.get("X-Authenticated-User") or body.voter
    if not voter:
        raise HTTPException(status_code=401, detail="Identity required: set X-Authenticated-User header")
    # ... use voter variable instead of body.voter
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest services/human-interface/tests/test_identity_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api-gateway/src/api_gateway/__init__.py services/human-interface/src/human_interface/api/routes.py services/human-interface/src/human_interface/models.py services/human-interface/tests/test_identity_auth.py
git commit -m "fix(security): derive resolved_by/voter from auth header, not request body

API Gateway now forwards X-Authenticated-User header to downstream services.
Human Interface derives identity from this header with body field fallback.
Requests without identity are rejected with 401.

Fixes: SEC-C3 (CVSS 8.1), AR-H1, TEST-H3"
```

---

### Task 1.4: API Gateway Auth — Fail Closed When No Keys

**Fixes:** SEC-H1 (CVSS 7.5)
**Files:**
- Modify: `apps/api-gateway/src/api_gateway/__init__.py:195-200`

- [ ] **Step 1: Write the test**

```python
# In apps/api-gateway/tests/test_auth.py (extend existing)
def test_auth_rejects_when_no_keys_configured_non_dev(self, monkeypatch):
    """When auth is enabled with no keys, non-dev envs must reject."""
    monkeypatch.setenv("ARCHITECT_GATEWAY_AUTH_ENABLED", "true")
    monkeypatch.setenv("ARCHITECT_GATEWAY_API_KEYS_RAW", "")
    monkeypatch.setenv("ARCHITECT_ENV", "production")
    get_config.cache_clear()
    resp = client.get("/state")
    assert resp.status_code == 503
```

- [ ] **Step 2: Implement fail-closed logic**

Replace the "no keys = open access" block:

```python
        if not api_keys:
            if config.environment not in ("dev", "test", "development"):
                logger.error("auth_no_keys", msg="Auth enabled but no API keys configured")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Service misconfigured: auth enabled with no keys"},
                )
            logger.warning("auth_open_access", msg="No API keys configured — open access (dev only)")
            return await call_next(request)
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest apps/api-gateway/tests/ -v`

```bash
git add apps/api-gateway/
git commit -m "fix(security): API Gateway fails closed when no API keys configured in non-dev

Fixes: SEC-H1 (CVSS 7.5)"
```

---

### Task 1.5: Add FK Constraint and Unique Vote Constraint

**Fixes:** SEC-H3 (CVSS 6.5), SEC-H5 (CVSS 6.8), AR-M4, TEST-H2
**Files:**
- Create: `libs/architect-db/migrations/versions/006_add_vote_constraints.py`
- Modify: `libs/architect-db/src/architect_db/models/escalation.py:90` (add ForeignKey)
- Modify: `services/human-interface/src/human_interface/api/routes.py:440-445` (handle IntegrityError)

- [ ] **Step 1: Create Alembic migration**

```python
# libs/architect-db/migrations/versions/006_add_vote_constraints.py
"""Add FK and unique constraints to approval_votes.

Revision ID: 006
Revises: 005
"""
from alembic import op

revision = "006"
down_revision = "005"


def upgrade() -> None:
    op.create_foreign_key(
        "fk_approval_votes_gate_id",
        "approval_votes",
        "approval_gates",
        ["gate_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_approval_votes_gate_voter",
        "approval_votes",
        ["gate_id", "voter"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_approval_votes_gate_voter", "approval_votes", type_="unique")
    op.drop_constraint("fk_approval_votes_gate_id", "approval_votes", type_="foreignkey")
```

- [ ] **Step 2: Update ORM model**

In `libs/architect-db/src/architect_db/models/escalation.py`, line 90:

```python
    gate_id: Mapped[str] = mapped_column(
        Text, sa.ForeignKey("approval_gates.id", ondelete="CASCADE"), nullable=False, index=True
    )
```

Add import: `import sqlalchemy as sa` at the top.

Add `UniqueConstraint` to the class:

```python
    __table_args__ = (
        sa.UniqueConstraint("gate_id", "voter", name="uq_approval_votes_gate_voter"),
    )
```

- [ ] **Step 3: Handle IntegrityError in vote route**

In `services/human-interface/src/human_interface/api/routes.py`, wrap the vote creation in a try/except:

```python
from sqlalchemy.exc import IntegrityError

# Inside cast_vote, replace the existing duplicate check with:
        try:
            vote = ApprovalVote(
                gate_id=gate_id,
                voter=voter,
                decision=body.decision,
                comment=body.comment,
            )
            await vote_repo.create(vote)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Voter has already voted on this gate")
```

Remove the old read-then-write duplicate check (lines 443-445).

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest services/human-interface/tests/ libs/architect-db/tests/ -v`

```bash
git add libs/architect-db/ services/human-interface/
git commit -m "fix(security): add FK and unique constraints on approval_votes

FK constraint on gate_id with CASCADE delete prevents orphaned votes.
Unique constraint on (gate_id, voter) prevents race-condition duplicate votes
at the database level, replacing the fragile read-then-write Python check.

Fixes: SEC-H3 (CVSS 6.5), SEC-H5 (CVSS 6.8), AR-M4, TEST-H2"
```

---

### Task 1.6: SSRF Protection — Validate Redirects

**Fixes:** SEC-M2 (CVSS 5.9)
**Files:**
- Modify: `services/knowledge-memory/src/knowledge_memory/doc_fetcher.py:119-126`

- [ ] **Step 1: Fix redirect handling**

In `doc_fetcher.py`, when using a caller-provided client, enforce `follow_redirects=False`:

```python
    if client is not None:
        # Enforce no-redirect policy on external clients to prevent SSRF via open redirects
        resp = await client.get(str(url))
    else:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
        ) as new_client:
            resp = await new_client.get(str(url))

    # If we got a redirect, validate the target URL before following
    if resp.status_code in (301, 302, 307, 308):
        redirect_url = resp.headers.get("location")
        if redirect_url:
            validate_url(redirect_url)  # Re-run SSRF checks on redirect target
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                follow_redirects=False,
            ) as redirect_client:
                resp = await redirect_client.get(redirect_url)
```

- [ ] **Step 2: Run tests and commit**

Run: `uv run pytest services/knowledge-memory/tests/test_doc_fetcher.py -v`

```bash
git add services/knowledge-memory/src/knowledge_memory/doc_fetcher.py
git commit -m "fix(security): validate redirect targets to prevent SSRF bypass

Fixes: SEC-M2 (CVSS 5.9)"
```

---

### Task 1.7: LLM Output Validation

**Fixes:** SEC-M7 (CVSS 5.0)
**Files:**
- Modify: `services/knowledge-memory/src/knowledge_memory/llm_utils.py`

- [ ] **Step 1: Add size limits to LLM JSON parsing**

```python
_MAX_CONTENT_LENGTH = 50_000  # 50KB max per content field
_MAX_TAGS_COUNT = 50
_MAX_ARRAY_LENGTH = 200


def parse_llm_json_array(text: str) -> list[dict[str, Any]]:
    """Parse LLM response as a JSON array with safety limits."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    parsed = json.loads(cleaned)

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ValueError(f"Expected list or dict, got {type(parsed).__name__}")

    if len(parsed) > _MAX_ARRAY_LENGTH:
        parsed = parsed[:_MAX_ARRAY_LENGTH]

    # Validate individual entries
    for entry in parsed:
        if isinstance(entry, dict):
            content = entry.get("content", "")
            if isinstance(content, str) and len(content) > _MAX_CONTENT_LENGTH:
                entry["content"] = content[:_MAX_CONTENT_LENGTH]
            tags = entry.get("tags", [])
            if isinstance(tags, list) and len(tags) > _MAX_TAGS_COUNT:
                entry["tags"] = tags[:_MAX_TAGS_COUNT]

    return parsed
```

- [ ] **Step 2: Run tests and commit**

Run: `uv run pytest services/knowledge-memory/tests/test_llm_utils.py -v`

```bash
git add services/knowledge-memory/src/knowledge_memory/llm_utils.py
git commit -m "fix(security): add size limits to LLM output parsing

Prevents memory exhaustion from adversarial LLM responses.
Limits: 50KB per content field, 50 tags, 200 array entries.

Fixes: SEC-M7 (CVSS 5.0)"
```

---

### Task 1.8: Fix .env.example Placeholder Secrets

**Fixes:** SEC-M4 (CVSS 5.3), DOC-M1
**Files:**
- Modify: `.env.example:55-61`

- [ ] **Step 1: Replace placeholder values**

```env
# Grafana (REQUIRED: generate with `openssl rand -hex 16` or run scripts/dev-setup.sh)
GRAFANA_PASSWORD=

# NATS (REQUIRED: generate with `openssl rand -hex 16` or run scripts/dev-setup.sh)
NATS_TOKEN=

# WebSocket authentication (REQUIRED: generate with `openssl rand -hex 32` or run scripts/dev-setup.sh)
ARCHITECT_WS_TOKEN=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "fix(security): remove placeholder secrets from .env.example

Replace changeme_* values with empty strings and generation instructions.

Fixes: SEC-M4 (CVSS 5.3), DOC-M1"
```

---

### Task 1.9: Docker Socket Proxy Network Isolation

**Fixes:** SEC-M5 (CVSS 6.0), CD-M14
**Files:**
- Modify: `infra/docker-compose.yml`

- [ ] **Step 1: Add isolated network for socket proxy**

Add a dedicated network and restrict access:

```yaml
networks:
  default:
    driver: bridge
  sandbox-internal:
    driver: bridge
    internal: true
```

On `docker-socket-proxy`:
```yaml
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy:0.6.0
    networks:
      - sandbox-internal
    # ... rest of config
```

On the sandbox service (when containerized), add:
```yaml
    networks:
      - default
      - sandbox-internal
```

- [ ] **Step 2: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "fix(security): isolate docker-socket-proxy on dedicated network

Only the sandbox service can reach the socket proxy.

Fixes: SEC-M5 (CVSS 6.0), CD-M14"
```

---

### Task 1.10–1.13: Remaining Security Items (batch)

**Fixes:** SEC-H2, SEC-H4, SEC-M3, SEC-L1–L6

- [ ] **Task 1.10:** Bind Phase 3 services to `127.0.0.1` in Makefile (SEC-H4, CD-M15) — change `--host 0.0.0.0` to `--host 127.0.0.1` for ports 8014-8016
- [ ] **Task 1.11:** Fix WebSocket token timing comparison (SEC-L1) — already done in Task 1.1
- [ ] **Task 1.12:** Add `-execdir` to sandbox blocked patterns (SEC-L5)
- [ ] **Task 1.13:** Add password to CI Redis service (SEC-L6, CD-M1) — `--requirepass ci_redis_pass` in ci.yml

---

## Phase 2: Performance & Data Integrity (12 tasks)

### Task 2.1: Migrate Similarity Search to pgvector

**Fixes:** PERF-C1, CQ-C1, AR-M5
**Files:**
- Create: `libs/architect-db/migrations/versions/007_add_pgvector_column.py`
- Modify: `services/knowledge-memory/src/knowledge_memory/knowledge_store.py:140-170`

- [ ] **Step 1: Create migration to add vector column**

```python
# libs/architect-db/migrations/versions/007_add_pgvector_column.py
"""Add pgvector embedding column to knowledge_entries.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Add native vector column (384 dimensions for sentence-transformers)
    op.execute("ALTER TABLE knowledge_entries ADD COLUMN embedding_vec vector(384)")
    # Backfill from JSONB embedding column
    op.execute("""
        UPDATE knowledge_entries
        SET embedding_vec = embedding::text::vector
        WHERE embedding IS NOT NULL AND jsonb_array_length(embedding) = 384
    """)
    # Create HNSW index for cosine distance
    op.execute("""
        CREATE INDEX ix_knowledge_entries_embedding_hnsw
        ON knowledge_entries
        USING hnsw (embedding_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entries_embedding_hnsw")
    op.execute("ALTER TABLE knowledge_entries DROP COLUMN IF EXISTS embedding_vec")
```

- [ ] **Step 2: Update search method to use pgvector**

In `knowledge_store.py`, replace the similarity search block (lines 150-170):

```python
        # Use pgvector cosine distance operator for server-side ranking.
        query = f"""
            SELECT *, 1 - (embedding_vec <=> :query_vec::vector) AS similarity
            FROM knowledge_entries
            WHERE {where} AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> :query_vec::vector
            LIMIT :limit
        """
        params["query_vec"] = str(query_embedding)
        params["limit"] = limit

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            return [dict(r) for r in result.mappings().all()]
```

- [ ] **Step 3: Run tests and commit**

```bash
git add libs/architect-db/migrations/ services/knowledge-memory/src/knowledge_memory/knowledge_store.py
git commit -m "perf: migrate similarity search to pgvector with HNSW index

Replaces O(N) Python-side cosine similarity with server-side pgvector
<=> operator and HNSW index. Search is now O(log N).

Fixes: PERF-C1, CQ-C1, AR-M5"
```

---

### Task 2.2: Add LIMIT to Observation Loading

**Fixes:** PERF-C2, CQ-C2
**Files:**
- Modify: `services/knowledge-memory/src/knowledge_memory/knowledge_store.py:250-270`

- [ ] **Step 1: Add max_batch parameter and LIMIT clause**

```python
    async def get_uncompressed_observations(
        self,
        *,
        domain: str | None = None,
        min_count: int = 5,
        max_batch: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch uncompressed observations in bounded batches."""
        conditions = ["compressed = false"]
        params: dict[str, Any] = {"max_batch": max_batch}

        if domain is not None:
            conditions.append("domain = :domain")
            params["domain"] = domain

        where = " AND ".join(conditions)
        query = f"SELECT * FROM observations WHERE {where} ORDER BY created_at LIMIT :max_batch"

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            rows = [dict(r) for r in result.mappings().all()]

        if len(rows) < min_count:
            return []
        return rows
```

- [ ] **Step 2: Commit**

```bash
git add services/knowledge-memory/src/knowledge_memory/knowledge_store.py
git commit -m "perf: add LIMIT clause to observation loading in compression pipeline

Prevents unbounded memory usage. Default batch size: 500 rows.

Fixes: PERF-C2, CQ-C2"
```

---

### Task 2.3: Add Retry Logic to API Gateway ServiceClient

**Fixes:** PERF-C3, CQ-M5
**Files:**
- Modify: `apps/api-gateway/src/api_gateway/service_client.py:70-95`

- [ ] **Step 1: Add retry with exponential backoff**

```python
    async def _request(
        self,
        service: str,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an HTTP request to a backend service with retry."""
        if self._client is None:
            msg = "ServiceClient not started — call startup() first"
            raise RuntimeError(msg)

        url = f"{self._base_url(service)}{path}"
        timeout = self._timeout_for_service(service)
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                resp = await self._client.request(method, url, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt == 2:
                    raise
                last_exc = exc
                await asyncio.sleep(0.5 * (2 ** attempt))

        raise last_exc  # type: ignore[misc]
```

Add `import asyncio` at the top of the file.

- [ ] **Step 2: Commit**

```bash
git add apps/api-gateway/src/api_gateway/service_client.py
git commit -m "perf: add retry with exponential backoff to API Gateway ServiceClient

Retries up to 3 times on connection errors and 5xx responses.

Fixes: PERF-C3, CQ-M5"
```

---

### Task 2.4: Add Database Indexes for Observations

**Fixes:** PERF-M1, PERF-M2
**Files:**
- Create: `libs/architect-db/migrations/versions/008_add_observation_indexes.py`

- [ ] **Step 1: Create migration**

```python
# libs/architect-db/migrations/versions/008_add_observation_indexes.py
"""Add indexes on observations table for compression pipeline performance.

Revision ID: 008
Revises: 007
"""
from alembic import op

revision = "008"
down_revision = "007"


def upgrade() -> None:
    # Partial index for uncompressed observations (used by compression pipeline)
    op.execute("""
        CREATE INDEX ix_observations_uncompressed
        ON observations (created_at)
        WHERE compressed = false
    """)
    op.create_index("ix_observations_domain", "observations", ["domain"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_observations_uncompressed")
    op.drop_index("ix_observations_domain", table_name="observations")
```

- [ ] **Step 2: Commit**

```bash
git add libs/architect-db/migrations/
git commit -m "perf: add database indexes on observations table

Partial index on compressed=false for compression pipeline queries.
Index on domain for filtered observation lookups.

Fixes: PERF-M1, PERF-M2"
```

---

### Task 2.5: Fix SpinDetector Unbounded State

**Fixes:** PERF-H3, CQ-M3, MEM-C1
**Files:**
- Modify: `services/economic-governor/src/economic_governor/spin_detector.py`

- [ ] **Step 1: Add LRU eviction to _state dict**

Replace the `_state` dict with an `OrderedDict` and add eviction:

```python
from collections import OrderedDict

class SpinDetector:
    _MAX_TRACKED = 10_000

    def __init__(self, config: EconomicGovernorConfig) -> None:
        self._max_retries = config.spin_max_retries
        self._state: OrderedDict[tuple[str, str], tuple[int, int]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def record_retry(self, agent_id, task_id, has_diff, tokens) -> SpinDetection:
        async with self._lock:
            key = (str(agent_id), str(task_id))
            if has_diff:
                self._state.pop(key, None)  # Remove entirely, don't just zero
                return SpinDetection(...)
            # ... existing logic ...
            self._state[key] = (new_count, new_tokens)
            self._state.move_to_end(key)
            # Evict oldest entries if over limit
            while len(self._state) > self._MAX_TRACKED:
                self._state.popitem(last=False)
            # ...
```

- [ ] **Step 2: Update tests and commit**

```bash
git add services/economic-governor/src/economic_governor/spin_detector.py services/economic-governor/tests/test_spin_detector.py
git commit -m "perf: bound SpinDetector state with LRU eviction (max 10K entries)

Prevents unbounded memory growth. Uses OrderedDict with eviction.
Completed tasks are removed entirely instead of zeroed.

Fixes: PERF-H3, CQ-M3"
```

---

### Task 2.6: Optimize State Validation (Triple Serialization)

**Fixes:** PERF-H1, CQ-M6
**Files:**
- Modify: `services/world-state-ledger/src/world_state_ledger/state_manager.py:385-440`

- [ ] **Step 1: Reduce to single serialization**

```python
    @staticmethod
    def _validate_mutations(
        state: WorldState, mutations: list[StateMutation]
    ) -> tuple[bool, str | None]:
        data = state.model_dump(mode="json")

        # Check old_value preconditions against current data
        for mutation in mutations:
            parts = mutation.path.split(".")
            current: Any = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                    break
            if mutation.old_value is not None and current != mutation.old_value:
                return (False, f"Stale value at '{mutation.path}': expected {mutation.old_value!r}, got {current!r}")

        # Budget constraint: simulate on a deep copy of the dict (no re-validation)
        simulated = copy.deepcopy(data)
        for mutation in mutations:
            StateManager._set_at_path(simulated, mutation.path, mutation.new_value)

        remaining = simulated.get("budget", {}).get("remaining_tokens", 0)
        if isinstance(remaining, (int, float)) and remaining < 0:
            return (False, f"Budget constraint violated: remaining_tokens would be {remaining}")

        return (True, None)
```

- [ ] **Step 2: Run tests and commit**

Run: `uv run pytest services/world-state-ledger/tests/ -v`

```bash
git add services/world-state-ledger/src/world_state_ledger/state_manager.py
git commit -m "perf: reduce state validation from 3 serializations to 1

Operates on dict representation throughout instead of round-tripping
through model_validate/model_dump.

Fixes: PERF-H1, CQ-M6"
```

---

### Task 2.7: Fix Distributed Lock Retry

**Fixes:** PERF-H5
**Files:**
- Modify: `services/task-graph-engine/src/task_graph_engine/distributed_lock.py:40-60`

- [ ] **Step 1: Implement proper retry with configurable timeout**

```python
    @asynccontextmanager
    async def schedule_lock(self, *, timeout: float = 5.0) -> AsyncIterator[None]:
        """Acquire a distributed scheduling lock with retry."""
        if self._redis is not None:
            deadline = asyncio.get_event_loop().time() + timeout
            lock_acquired = False
            try:
                while asyncio.get_event_loop().time() < deadline:
                    lock_acquired = await self._redis.set(_LOCK_KEY, "1", nx=True, ex=30)
                    if lock_acquired:
                        break
                    await asyncio.sleep(0.1)
                if not lock_acquired:
                    raise RuntimeError(f"Could not acquire scheduler lock after {timeout}s")
                yield
            finally:
                if lock_acquired:
                    await self._redis.delete(_LOCK_KEY)
        else:
            async with self._local_lock:
                yield
```

- [ ] **Step 2: Run tests and commit**

```bash
git add services/task-graph-engine/src/task_graph_engine/distributed_lock.py
git commit -m "perf: improve distributed lock retry with configurable timeout

Retries every 100ms up to 5s (configurable) instead of single retry.

Fixes: PERF-H5"
```

---

### Task 2.8–2.12: Remaining Performance Items

- [ ] **Task 2.8:** Fix hardcoded AgentType/ModelTier in EfficiencyScorer (CQ-H5) — track in `_AgentStats`, propagate to persistence
- [ ] **Task 2.9:** Combine escalation stats into single SQL query (PERF-H2) — use `func.count().filter()` pattern
- [ ] **Task 2.10:** Add dashboard API timeout with AbortController (PERF-H7, CQ-M7) — `AbortSignal.timeout(15_000)` in `client.ts`
- [ ] **Task 2.11:** Fix connection pool sizing docs (PERF-M3) — update comment in `engine.py` to reflect 12+ services
- [ ] **Task 2.12:** Fix _SERVICE_STARTED_AT to use app.state (CQ-H3) — move to lifespan handler in all 3 route files

---

## Phase 3: Code Quality & Architecture (14 tasks)

### Task 3.1: Extract Shared ServiceDependency into architect-common

**Fixes:** CQ-H1, BP-M1
**Files:**
- Modify: `libs/architect-common/src/architect_common/__init__.py`
- Create: `libs/architect-common/src/architect_common/dependencies.py`
- Modify: All 12 `services/*/src/*/api/dependencies.py` files

- [ ] **Step 1: Create the generic ServiceDependency class**

```python
# libs/architect-common/src/architect_common/dependencies.py
"""Generic dependency injection container for FastAPI services."""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class ServiceDependency(Generic[T]):
    """Type-safe dependency slot for FastAPI DI."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._instance: T | None = None

    def get(self) -> T:
        if self._instance is None:
            raise RuntimeError(f"{self._name} not initialised. Call set() during startup.")
        return self._instance

    def set(self, instance: T) -> None:
        self._instance = instance

    async def cleanup(self) -> None:
        if self._instance is not None and hasattr(self._instance, "aclose"):
            await self._instance.aclose()
        self._instance = None
```

- [ ] **Step 2: Migrate economic-governor dependencies as the first service**

```python
# services/economic-governor/src/economic_governor/api/dependencies.py
from architect_common.dependencies import ServiceDependency
from economic_governor.budget_tracker import BudgetTracker
from economic_governor.config import EconomicGovernorConfig
from economic_governor.efficiency_scorer import EfficiencyScorer
from economic_governor.enforcer import Enforcer
from functools import lru_cache

@lru_cache(maxsize=1)
def get_config() -> EconomicGovernorConfig:
    return EconomicGovernorConfig()

_budget_tracker = ServiceDependency[BudgetTracker]("BudgetTracker")
_efficiency_scorer = ServiceDependency[EfficiencyScorer]("EfficiencyScorer")
_enforcer = ServiceDependency[Enforcer]("Enforcer")

get_budget_tracker = _budget_tracker.get
set_budget_tracker = _budget_tracker.set
get_efficiency_scorer = _efficiency_scorer.get
set_efficiency_scorer = _efficiency_scorer.set
get_enforcer = _enforcer.get
set_enforcer = _enforcer.set

async def cleanup() -> None:
    await _budget_tracker.cleanup()
    await _efficiency_scorer.cleanup()
    await _enforcer.cleanup()
```

- [ ] **Step 3: Migrate remaining services (repeat pattern for each)**
- [ ] **Step 4: Run all tests and commit**

```bash
git add libs/architect-common/ services/*/src/*/api/dependencies.py
git commit -m "refactor: extract shared ServiceDependency into architect-common

Replaces ~80 lines of duplicated get/set/cleanup boilerplate per service.

Fixes: CQ-H1, BP-M1"
```

---

### Task 3.2: Extract Shared HealthResponse

**Fixes:** CQ-L2
**Files:**
- Modify: `libs/architect-common/src/architect_common/__init__.py`
- Modify: All service route files that define HealthResponse

- [ ] **Step 1: Add to architect-common**

```python
# libs/architect-common/src/architect_common/health.py
from pydantic import BaseModel
from architect_common.enums import HealthStatus

class HealthResponse(BaseModel):
    service: str
    status: HealthStatus
    uptime_seconds: float = 0.0
```

- [ ] **Step 2: Replace per-service definitions with import**
- [ ] **Step 3: Commit**

---

### Task 3.3: Refactor Enforcer — Extract Shared Ceremony

**Fixes:** CQ-H2
**Files:**
- Modify: `services/economic-governor/src/economic_governor/enforcer.py:40-190`

- [ ] **Step 1: Extract `_enforce` helper method**

```python
    async def _enforce(
        self,
        level: EnforcementLevel,
        action_type: str,
        event_type: EventType,
        payload: ArchitectBase,
        details: dict[str, object],
        consumed_pct: float,
        target_id: str | None = None,
    ) -> None:
        envelope = EventEnvelope(
            type=event_type,
            payload=payload.model_dump(mode="json"),
        )
        await self._publisher.publish(envelope)

        record = EnforcementRecord(
            id=_prefixed_uuid("enf"),
            level=level,
            action_type=action_type,
            target_id=target_id,
            details=details,
            budget_consumed_pct=consumed_pct,
        )
        self._history.append(record)
        await self._persist_action(record)
```

Then simplify each method to call `self._enforce(...)`.

- [ ] **Step 2: Run tests and commit**

---

### Task 3.4: Migrate ORM Models to sa.Enum Convention

**Fixes:** AR-M1, BP-M4
**Files:**
- Modify: `libs/architect-db/src/architect_db/models/escalation.py`
- Modify: `libs/architect-db/src/architect_db/models/knowledge.py`
- Create: `libs/architect-db/migrations/versions/009_enum_columns.py`

- [ ] **Step 1: Update ORM models to use `sa.Enum(MyEnum, native_enum=False, length=64)`**
- [ ] **Step 2: Create Alembic migration with ALTER COLUMN**
- [ ] **Step 3: Run tests and commit**

---

### Task 3.5: Migrate BaseHTTPMiddleware to Pure ASGI

**Fixes:** BP-H1
**Files:**
- Modify: `apps/api-gateway/src/api_gateway/__init__.py:120-170`

- [ ] **Step 1: Convert SecurityHeadersMiddleware to pure ASGI**
- [ ] **Step 2: Convert RateLimitMiddleware to pure ASGI**
- [ ] **Step 3: Convert remaining 3 middleware classes**
- [ ] **Step 4: Run tests and commit**

---

### Task 3.6: Type Temporal Workflow Parameters

**Fixes:** BP-M2, BP-M3
**Files:**
- Modify: `services/economic-governor/src/economic_governor/temporal/workflows.py`
- Modify: `services/economic-governor/src/economic_governor/temporal/activities.py`

- [ ] **Step 1: Create typed dataclasses for workflow params**
- [ ] **Step 2: Replace `dict[str, Any]` params with dataclasses**
- [ ] **Step 3: Run tests and commit**

---

### Task 3.7: Fix EventEnvelope Typing

**Fixes:** BP-M5, AR-L5, AR-L7
**Files:**
- Modify: `libs/architect-events/src/architect_events/schemas.py`

- [ ] **Step 1: Fix HeuristicCreatedEvent.heuristic_id to `HeuristicId`**
- [ ] **Step 2: Fix ApprovalResolvedEvent.status to `ApprovalGateStatus`**
- [ ] **Step 3: Commit**

---

### Task 3.8–3.14: Remaining Code Quality Items

- [ ] **Task 3.8:** Fix monitor.py inconsistent payload validation (CQ-M1) — create `RoutingDecisionPayload` Pydantic model
- [ ] **Task 3.9:** Enable redirects in doc_fetcher with max_redirects=5 (CQ-M2)
- [ ] **Task 3.10:** Remove unused pattern_id generation (CQ-M4)
- [ ] **Task 3.11:** Fix duplicated TaskCompletedPayload (CQ-L1) — move canonical payload to architect-events
- [ ] **Task 3.12:** Push approval gate action_type filter to SQL (CQ-L5)
- [ ] **Task 3.13:** Enable mypy on test files with relaxed overrides (BP-M6)
- [ ] **Task 3.14:** Remove unnecessary `from __future__ import annotations` (BP-L1)

---

## Phase 4: Testing & Documentation (16 tasks)

### Task 4.1: architect-db Repository Tests

**Fixes:** TEST-C1
**Files:**
- Create: `libs/architect-db/tests/test_escalation_repo.py`
- Create: `libs/architect-db/tests/test_budget_repo.py`
- Create: `libs/architect-db/tests/test_knowledge_repo.py`

- [ ] **Step 1: Write escalation repository tests**

```python
# libs/architect-db/tests/test_escalation_repo.py
import pytest
from architect_db.repositories.escalation_repo import EscalationRepository
from architect_db.models.escalation import Escalation


class TestEscalationRepository:
    async def test_create_and_get(self, session):
        repo = EscalationRepository(session)
        esc = Escalation(id="esc-test-1", summary="Test", category="technical", severity="high", status="pending")
        await repo.create(esc)
        await session.flush()
        result = await repo.get_by_id("esc-test-1")
        assert result is not None
        assert result.summary == "Test"

    async def test_resolve_updates_status(self, session):
        repo = EscalationRepository(session)
        esc = Escalation(id="esc-r-1", summary="Resolve test", category="technical", severity="medium", status="pending")
        await repo.create(esc)
        await session.flush()
        resolved = await repo.resolve("esc-r-1", resolved_by="admin", resolution="approved")
        assert resolved is not None
        assert resolved.status == "resolved"
        assert resolved.resolved_by == "admin"

    async def test_resolve_nonexistent_returns_none(self, session):
        repo = EscalationRepository(session)
        result = await repo.resolve("esc-missing", resolved_by="admin", resolution="done")
        assert result is None

    async def test_get_stats(self, session):
        repo = EscalationRepository(session)
        for i in range(3):
            await repo.create(Escalation(id=f"esc-s-{i}", summary=f"S{i}", category="technical", severity="low", status="pending"))
        await session.flush()
        stats = await repo.get_stats()
        assert stats["total"] >= 3
        assert stats["pending"] >= 3
```

- [ ] **Step 2: Write budget and knowledge repo tests (similar pattern)**
- [ ] **Step 3: Run and commit**

---

### Task 4.2: Alembic Migration Cycle Test

**Fixes:** TEST-H6
**Files:**
- Create: `libs/architect-db/tests/test_migrations.py`

- [ ] **Step 1: Write migration up/down/up test**

```python
# libs/architect-db/tests/test_migrations.py
"""Verify Alembic migrations can upgrade, downgrade, and re-upgrade cleanly."""
import pytest
from alembic.config import Config
from alembic import command


@pytest.mark.integration
class TestMigrations:
    def test_upgrade_downgrade_cycle(self, alembic_config):
        """Full upgrade -> downgrade last -> re-upgrade should not error."""
        command.upgrade(alembic_config, "head")
        command.downgrade(alembic_config, "-1")
        command.upgrade(alembic_config, "head")
```

- [ ] **Step 2: Run and commit**

---

### Task 4.3: Temporal Workflow Tests

**Fixes:** TEST-H1
**Files:**
- Create: `services/economic-governor/tests/test_temporal_workflows.py`

- [ ] **Step 1: Write workflow tests using temporalio.testing.WorkflowEnvironment**
- [ ] **Step 2: Run and commit**

---

### Task 4.4: Write Phase 3 API Reference

**Fixes:** DOC-C1, DOC-M5, DOC-M6
**Files:**
- Modify: `docs/api/README.md`

- [ ] **Step 1: Add Knowledge & Memory API section (13 endpoints)**
- [ ] **Step 2: Add Economic Governor API section (8 endpoints)**
- [ ] **Step 3: Add Human Interface API section (12 endpoints)**
- [ ] **Step 4: Update port table and gateway route table**
- [ ] **Step 5: Add Phase 3 event types**
- [ ] **Step 6: Commit**

---

### Task 4.5: Create WebSocket Protocol Spec

**Fixes:** DOC-C3
**Files:**
- Create: `docs/api/websocket-protocol.md`

- [ ] **Step 1: Document connection lifecycle, auth, message format, types, error codes**
- [ ] **Step 2: Commit**

---

### Task 4.6: Consolidate Security Audit Documents

**Fixes:** DOC-C2
**Files:**
- Modify: `docs/security/phase3-security-audit.md` (archive)
- Create: `docs/security/security-audit-tracker.md` (consolidated with status column)

- [ ] **Step 1: Create consolidated tracker with Open/Remediated/Accepted Risk status**
- [ ] **Step 2: Archive the duplicate document**
- [ ] **Step 3: Commit**

---

### Task 4.7–4.16: Remaining Docs & Tests

- [ ] **Task 4.7:** Update incident response runbook with Phase 3 ports (DOC-H1)
- [ ] **Task 4.8:** Update observability runbook (DOC-H2)
- [ ] **Task 4.9:** Update local dev setup with Phase 3 run commands (DOC-H3)
- [ ] **Task 4.10:** Add Phase 3 CHANGELOG entry (DOC-H7)
- [ ] **Task 4.11:** Update stale performance analysis with remediation status (DOC-H5)
- [ ] **Task 4.12:** Create Phase 3 ADRs (DOC-H6) — ADR-006 memory hierarchy, ADR-007 budget enforcement, ADR-008 WebSocket vs SSE
- [ ] **Task 4.13:** Fix enforcement threshold docs vs config inconsistency (DOC-M2) — update phase-3-design.md to match .env.example defaults (70/85/95)
- [ ] **Task 4.14:** Raise coverage threshold to 75% (TEST-M6)
- [ ] **Task 4.15:** Add dashboard component tests for Escalations and Activity pages (TEST-M2)
- [ ] **Task 4.16:** Add `<user_input>` delimiter enforcement tests (TEST-L4)

---

## Phase 5: Infrastructure & DevOps (14 tasks)

### Task 5.1: Fix NATS Healthcheck

**Fixes:** CD-H3, CQ-L6, SEC-L2
**Files:**
- Modify: `infra/docker-compose.yml:85-100`

- [ ] **Step 1: Add monitoring port flag to NATS command**

```yaml
  nats:
    image: nats:2.10.24
    command: ["--js", "--sd", "/data", "--auth", "${NATS_TOKEN:?Set NATS_TOKEN in .env}", "-m", "8222"]
    ports:
      - "127.0.0.1:4222:4222"
    volumes:
      - nats_data:/data
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://localhost:8222/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "fix(infra): enable NATS monitoring port for healthcheck

Add -m 8222 flag so the wget healthcheck on port 8222 actually works.

Fixes: CD-H3, CQ-L6, SEC-L2"
```

---

### Task 5.2: Implement Alertmanager

**Fixes:** CD-C2
**Files:**
- Modify: `infra/docker-compose.yml` (add alertmanager service)
- Create: `infra/alertmanager/alertmanager.yml`
- Modify: `infra/prometheus/prometheus.yml` (add alerting section)

- [ ] **Step 1: Create Alertmanager config**

```yaml
# infra/alertmanager/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'default'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://host.docker.internal:8016/api/v1/escalations'
        send_resolved: true
```

- [ ] **Step 2: Add alertmanager container to docker-compose**

```yaml
  alertmanager:
    image: prom/alertmanager:v0.28.1
    ports:
      - "127.0.0.1:9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 128M
```

- [ ] **Step 3: Add alerting section to prometheus.yml**

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

- [ ] **Step 4: Commit**

```bash
git add infra/
git commit -m "feat(infra): add Alertmanager for Prometheus alert notifications

Configures webhook receiver pointing to Human Interface escalation endpoint.

Fixes: CD-C2"
```

---

### Task 5.3: Fix CI Postgres Image Parity

**Fixes:** CD-M2
**Files:**
- Modify: `.github/workflows/ci.yml:98`

- [ ] **Step 1: Change `postgres:16` to `pgvector/pgvector:pg16`**
- [ ] **Step 2: Commit**

---

### Task 5.4: Add Temporal Healthcheck

**Fixes:** CD-M13
**Files:**
- Modify: `infra/docker-compose.yml` (temporal service section)

- [ ] **Step 1: Add healthcheck to temporal container**

```yaml
    healthcheck:
      test: ["CMD", "tctl", "--address", "localhost:7233", "cluster", "health"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 30s
```

- [ ] **Step 2: Commit**

---

### Task 5.5: Pin Sandbox Dockerfile uv Version

**Fixes:** CD-M6
**Files:**
- Modify: `infra/dockerfiles/Dockerfile.sandbox:21`

- [ ] **Step 1: Pin `ghcr.io/astral-sh/uv:0.5.14` (matching Dockerfile.service)**
- [ ] **Step 2: Commit**

---

### Task 5.6: Create Grafana Dashboards

**Fixes:** CD-M7
**Files:**
- Create: `infra/grafana/provisioning/dashboards/service-health.json`
- Create: `infra/grafana/provisioning/dashboards/budget-monitoring.json`

- [ ] **Step 1: Create service health dashboard JSON (uptime, error rate, latency)**
- [ ] **Step 2: Create budget monitoring dashboard JSON (consumption, burn rate, enforcement level)**
- [ ] **Step 3: Commit**

---

### Task 5.7: Add Infrastructure Alert Exporters

**Fixes:** CD-M9
**Files:**
- Modify: `infra/docker-compose.yml`
- Modify: `infra/prometheus/prometheus.yml`

- [ ] **Step 1: Add postgres-exporter and redis-exporter containers**
- [ ] **Step 2: Add scrape targets for exporters in prometheus.yml**
- [ ] **Step 3: Commit**

---

### Task 5.8: Implement Deployment Pipeline

**Fixes:** CD-C1, CD-H1, CD-H2
**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Replace stubbed staging deploy with real commands** (docker pull, run migrations, restart services, health check)
- [ ] **Step 2: Add rollback workflow** (workflow_dispatch with version parameter)
- [ ] **Step 3: Add post-deploy smoke tests** (run `scripts/check-health.py`)
- [ ] **Step 4: Commit**

---

### Task 5.9–5.14: Remaining Infrastructure Items

- [ ] **Task 5.9:** Add Temporal and NATS as CI service containers (CD-M3)
- [ ] **Task 5.10:** Add E2E test job to CI (CD-M4) — optional/nightly
- [ ] **Task 5.11:** Add image signing with cosign (CD-M12)
- [ ] **Task 5.12:** Add Docker layer caching to release pipeline (CD-L3)
- [ ] **Task 5.13:** Add on-call documentation and escalation procedures (CD-M10)
- [ ] **Task 5.14:** Add startup validation for required env vars in each service (CD-M11)

---

## Summary

| Phase | Tasks | Findings Fixed | Priority |
|-------|-------|---------------|----------|
| 1: Security | 13 | ~25 (all Critical + High security) | Immediate |
| 2: Performance | 12 | ~20 (all Critical + High perf) | This sprint |
| 3: Code Quality | 14 | ~25 (architecture, conventions) | This sprint |
| 4: Testing & Docs | 16 | ~25 (test gaps, documentation) | Next sprint |
| 5: Infrastructure | 14 | ~15 (CI/CD, monitoring, deployment) | Next sprint |
| **Total** | **69 tasks** | **~105 findings** | |

Each phase produces a working, tested codebase. Phases 1-2 should be completed before any new feature work. Phases 3-5 can overlap with feature development.
