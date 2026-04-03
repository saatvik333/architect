# Phase 3: Intelligence, Autonomy & Human Interface

## Overview

Phase 3 adds three components to ARCHITECT: persistent learning (Knowledge & Memory), cost governance (Economic Governor), and human-in-the-loop workflows (Human Interface). These complete the system's ability to learn from past work, enforce budget constraints, and escalate decisions to humans when needed.

## Components

| Component | Port | Temporal Queue | Config Prefix |
|-----------|------|----------------|---------------|
| Knowledge & Memory (9) | 8014 | knowledge-memory | KM_ |
| Economic Governor (10) | 8015 | economic-governor | ECON_GOV_ |
| Human Interface (14) | 8016 | human-interface | HUMAN_INTERFACE_ |

## Knowledge & Memory (Component 9)

### Purpose
5-layer memory hierarchy enabling agents to learn from past work and apply knowledge to future tasks.

### Memory Layers
- **L0 Working** — In-process, task-scoped, TTL-evicted
- **L1 Project** — Postgres + pgvector, project lifetime
- **L2 Patterns** — Reusable code patterns extracted from observations, permanent
- **L3 Heuristics** — "When X, do Y" rules synthesized from patterns, permanent
- **L4 Meta-Strategy** — Cross-domain orchestration improvements, permanent

### Pipelines
- **Knowledge Acquisition**: fetch docs -> summarize -> mine examples -> extract patterns -> tag versions -> store
- **Memory Compression**: observations -> cluster by embedding similarity -> extract patterns -> synthesize heuristics -> derive meta-strategies

### Key Design Decisions
- Complements Codebase Comprehension (Component 5) at a higher abstraction level — stores knowledge, not raw code
- Uses same embedding model (all-MiniLM-L6-v2, 384-dim) for compatibility
- LLM-powered pattern extraction and heuristic synthesis via architect-llm

### Integration Points
- Subscribes to TASK_COMPLETED, TASK_FAILED, EVAL_COMPLETED via Redis Streams
- Publishes KNOWLEDGE_UPDATE via NATS JetStream
- Calls Codebase Comprehension API for code context

## Economic Governor (Component 10)

### Purpose
Real-time budget tracking with progressive enforcement, efficiency scoring, and spin detection.

### Progressive Enforcement

Thresholds are configurable via environment variables (`ECON_GOV_ALERT_THRESHOLD_PCT`, `ECON_GOV_RESTRICT_THRESHOLD_PCT`, `ECON_GOV_HALT_THRESHOLD_PCT`). Recommended defaults from `.env.example`:

- **70% ALERT** — Publish warning event, notify Human Interface
- **85% RESTRICT** — Force tier downgrade to TIER_3, pause non-critical tasks
- **95% HALT** — Cancel all tasks, generate progress report, escalate to human

Code defaults (if env vars are unset): 80% / 95% / 100%.

### Budget Allocation Formula
```
Project budget = f(estimated_complexity, priority, deadline)
Breakdown: Spec 5% | Planning 10% | Implementation 40% | Testing 20% | Review 5% | Debugging 15% | Contingency 5%
```

### Efficiency Scoring
```
efficiency = (tasks_completed * quality_score) / tokens_consumed
```

### Spin Detection
Agent killed after 3 consecutive retries with no meaningful diff.

### Key Design Decisions
- In-memory budget tracker with periodic DB snapshots (crash loses at most one poll interval)
- Polls Multi-Model Router /api/v1/route/costs for cost data
- Event-driven tier downgrade via BudgetTierDowngradeEvent (Router subscribes)
- WSL proposals for budget state updates (follows proposal pipeline)

## Human Interface (Component 14)

### Purpose
Escalation management, approval gates, and dashboard UI for human-in-the-loop workflows.

### Escalation Protocol
```python
if confidence < 0.6: ESCALATE
if security_critical: ESCALATE
if cost_impact > 20% budget: ESCALATE
if architectural_fork: ESCALATE_WITH_OPTIONS
if confidence < 0.9: PROCEED_WITH_FLAG
else: PROCEED
```

### Approval Gates
Configurable approval requirements per action type. Votes tracked individually. Auto-resolve when sufficient approvals received.

### Dashboard Extensions
4 new pages added to the React/TypeScript dashboard:
- **Escalations** — Pending decisions with DECISION NEEDED format, approve/reject/custom actions
- **Progress** — Task graph, budget, tests, coverage metrics with real-time updates
- **Budget** — Budget consumption, phase breakdown, warnings (graceful fallback if EG unavailable)
- **Activity** — Real-time event stream via WebSocket + polling fallback

### WebSocket Architecture
Human Interface service -> API Gateway WS proxy -> Dashboard browser client. Message types: escalation_created, escalation_resolved, approval_gate_created, approval_vote_cast, event, progress.update, ping.

### Key Design Decisions
- WebSocket for time-sensitive escalation notifications, polling fallback for reliability
- DB-backed escalation/approval state via architect-db repositories
- Temporal workflows for escalation timeout and approval gate coordination

## Database Schema (Migration 005)

10 new tables across three services:
- Knowledge: knowledge_entries, knowledge_observations, heuristic_rules, meta_strategies
- Budget: budget_records, agent_efficiency_scores, enforcement_actions
- Human Interface: escalations, approval_gates, approval_votes

## Shared Library Additions

### architect-common
- 5 branded ID types: KnowledgeId, PatternId, HeuristicId, EscalationId, ApprovalGateId
- 8 new enums: EnforcementLevel, BudgetPhase, MemoryLayer, ContentType, ObservationType, EscalationCategory, EscalationSeverity, EscalationStatus, ApprovalGateStatus
- 15 new EventType variants
- Error types for Knowledge & Memory and Human Interface

### architect-events
- 12 new event schema models for budget enforcement, knowledge lifecycle, and escalation management

### architect-db
- 10 new ORM models with repositories
- Combined Alembic migration 005_add_phase3_tables

## Known Limitations

- **Knowledge query lacks semantic ranking** — The knowledge query endpoint does not generate embeddings for query text; results are returned in insertion order, not by semantic relevance.
- **Stub Temporal activities** — Some Temporal activities in Knowledge & Memory still return stub data (`summarize_documentation`, `publish_knowledge_update`).
- **Working memory (L0) is in-process only** — L0 memory is not backed by Redis yet; it is lost on service restart.
- **Python-side cosine similarity** — Knowledge search computes cosine similarity in Python rather than using pgvector; a pgvector-based migration is planned.
- **WebSocket token not validated against auth backend** — Token presence is checked but not verified against an authentication backend; any non-empty token is accepted.
- **Economic Governor in-memory state between persistence points** — Budget state is persisted to Postgres on enforcement transitions and restored on startup, but consumption tracking between persistence points is per-instance and lost on crash.
