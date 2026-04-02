# ARCHITECT API Reference -- Phase 1 & 2 Services

This document covers the REST APIs exposed by the Phase 1 and Phase 2 services. All services are built on FastAPI, communicate via JSON request/response bodies, and follow shared conventions described below.

## General Conventions

### Base URL Pattern

Each service binds to a dedicated port on `localhost` during local development:

| Service              | Port |
|----------------------|------|
| **API Gateway**          | 8000 |
| World State Ledger       | 8001 |
| Task Graph Engine        | 8003 |
| Execution Sandbox        | 8007 |
| Evaluation Engine        | 8008 |
| Coding Agent             | 8009 |
| Spec Engine              | 8010 |
| Multi-Model Router       | 8011 |
| Codebase Comprehension   | 8012 |
| Agent Comm Bus           | 8013 |
| Knowledge & Memory       | 8014 |
| Economic Governor        | 8015 |
| Human Interface          | 8016 |

### API Gateway

The API Gateway (`apps/api-gateway`) is the unified HTTP entry point. All client requests should go through the gateway, which proxies to backend services.

**Gateway routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Aggregate health check across all services |
| `POST` | `/api/v1/tasks` | Submit a new task specification |
| `GET` | `/api/v1/tasks` | List all tasks (optional `status` and `type` query filters) |
| `GET` | `/api/v1/tasks/{task_id}` | Retrieve task status |
| `GET` | `/api/v1/tasks/{task_id}/logs` | Retrieve task logs |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | Cancel a running task |
| `GET` | `/api/v1/tasks/{task_id}/proposals` | List proposals for a task |
| `GET` | `/api/v1/proposals` | List proposals (optional `task_id` query filter) |
| `GET` | `/api/v1/proposals/{proposal_id}` | Get a single proposal |
| `GET` | `/api/v1/state` | Get current world state |
| `POST` | `/api/v1/state/proposals` | Submit a raw proposal |
| `POST` | `/api/v1/specs` | Submit NL description for spec parsing |
| `GET` | `/api/v1/specs/{spec_id}` | Retrieve a parsed specification |
| `POST` | `/api/v1/specs/{spec_id}/clarify` | Answer clarification questions |
| `POST` | `/api/v1/route` | Get a model routing decision |
| `GET` | `/api/v1/route/stats` | Retrieve routing statistics |
| `POST` | `/api/v1/index` | Index a codebase directory |
| `GET` | `/api/v1/context` | Get relevant code context for a task |
| `GET` | `/api/v1/symbols` | Search for code symbols |
| `GET` | `/api/v1/bus/stats` | Get message bus statistics |
| `GET` | `/api/v1/search` | Semantic code search (proxied to Codebase Comprehension) |
| `POST` | `/api/v1/bus/publish` | Publish a message to the agent bus |

Configuration is via environment variables with `ARCHITECT_GATEWAY_` prefix (e.g., `ARCHITECT_GATEWAY_TASK_GRAPH_URL`).

### Error Format

All error responses use a standard JSON body:

```json
{
  "detail": "Human-readable error message describing what went wrong."
}
```

FastAPI validation errors (422) include field-level detail:

```json
{
  "detail": [
    {
      "loc": ["body", "mutations", 0, "path"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

### Health Endpoint

Every service exposes a health check at:

```
GET /health
```

**Response** (200 OK):

```json
{
  "status": "healthy",
  "service": "<service-name>",
  "version": "0.1.0"
}
```

The `status` field is one of: `healthy`, `degraded`, `down`, `unknown` (see `HealthStatus` enum).

### ID Formats

ARCHITECT uses branded ID types with prefixes:

| Type         | Prefix     | Example                                  |
|--------------|------------|------------------------------------------|
| `TaskId`     | `task-`    | `task-01hzv4k8m3n7p2q5r8s0t6w9`          |
| `AgentId`    | `agent-`   | `agent-01hzv4k8m3n7p2q5r8s0t6w9`         |
| `ProposalId` | `prop-`    | `prop-01hzv4k8m3n7p2q5r8s0t6w9`          |
| `EventId`    | `evt-`     | `evt-01hzv4k8m3n7p2q5r8s0t6w9`           |

### Common Enums

**StatusEnum**: `pending`, `running`, `completed`, `failed`, `blocked`, `cancelled`

**EvalVerdict**: `pass`, `fail_soft`, `fail_hard`

**TaskType**: `implement_feature`, `write_test`, `review_code`, `fix_bug`, `refactor`

**ModelTier**: `tier_1` (Opus-class), `tier_2` (Sonnet-class), `tier_3` (Haiku-class)

---

## 1. World State Ledger API (Port 8001)

The World State Ledger maintains a versioned, event-sourced view of the entire system state. All mutations flow through the proposal pipeline: an agent submits a proposal, the system validates it, and if accepted, the mutation is atomically committed and a new version is created.

### GET /state

Returns the current world state snapshot. Results are served from the Redis cache when available (30-second TTL), falling back to Postgres.

**Response** (200 OK):

```json
{
  "version": 42,
  "state_snapshot": {
    "budget": {
      "total_tokens": 10000000,
      "consumed_tokens": 245000,
      "remaining_tokens": 9755000
    },
    "tasks": { ... },
    "agents": { ... }
  },
  "updated_at": "2026-03-13T10:30:00Z"
}
```

### GET /state/{version}

Returns a historical world state by version number. Since the ledger is append-only, every past version is preserved.

**Path Parameters:**

| Name    | Type | Required | Description                       |
|---------|------|----------|-----------------------------------|
| version | int  | yes      | The ledger version number to fetch |

**Response** (200 OK):

```json
{
  "version": 17,
  "state_snapshot": { ... },
  "updated_at": "2026-03-13T09:15:00Z",
  "proposal_id": "prop-01hzv4k8m3n7p2q5r8s0t6w9"
}
```

**Errors:**

| Status | Condition                             |
|--------|---------------------------------------|
| 404    | No snapshot exists for the given version |

### POST /proposals

Submit a state mutation proposal. Proposals are validated before being committed. Each proposal specifies one or more dot-path-based mutations with expected old values for optimistic concurrency.

**Request Body:**

```json
{
  "agent_id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "mutations": [
    {
      "path": "budget.consumed_tokens",
      "old_value": 245000,
      "new_value": 248500
    }
  ],
  "rationale": "Token usage update after code generation step."
}
```

| Field     | Type              | Required | Description                                          |
|-----------|-------------------|----------|------------------------------------------------------|
| agent_id  | string (AgentId)  | yes      | The agent submitting the proposal                    |
| task_id   | string (TaskId)   | yes      | The task this mutation relates to                    |
| mutations | array of Mutation | yes      | One or more field-level changes                      |
| rationale | string            | no       | Human-readable explanation for the mutation          |

Each **Mutation** object:

| Field     | Type   | Required | Description                                |
|-----------|--------|----------|--------------------------------------------|
| path      | string | yes      | Dot-delimited path into the state tree     |
| old_value | any    | yes      | Expected current value (for CAS semantics) |
| new_value | any    | yes      | Desired new value                          |

**Response** (201 Created):

```json
{
  "proposal_id": "prop-01hzv4k8m3n7p2q5r8s0t6w9",
  "status": "pending"
}
```

### POST /proposals/{proposal_id}/commit

Validate and commit a pending proposal. The system checks that the current ledger state matches the expected `old_value` for each mutation. If all checks pass, a new ledger version is created atomically.

**Path Parameters:**

| Name        | Type   | Required | Description        |
|-------------|--------|----------|--------------------|
| proposal_id | string | yes      | The proposal to commit |

**Response** (200 OK):

```json
{
  "accepted": true,
  "version": 43,
  "reason": null
}
```

On rejection:

```json
{
  "accepted": false,
  "version": null,
  "reason": "Conflict: budget.consumed_tokens has been modified since proposal creation (expected 245000, found 247000)."
}
```

**Errors:**

| Status | Condition                      |
|--------|--------------------------------|
| 404    | Proposal not found             |

### GET /events

Query the append-only event log. Supports filtering by event type, task, and agent.

**Query Parameters:**

| Name       | Type   | Default | Description                               |
|------------|--------|---------|-------------------------------------------|
| event_type | string | (none)  | Filter by EventType enum value            |
| task_id    | string | (none)  | Filter events related to a specific task  |
| agent_id   | string | (none)  | Filter events related to a specific agent |
| limit      | int    | 100     | Maximum number of events to return        |
| offset     | int    | 0       | Number of events to skip (pagination)     |

**Response** (200 OK):

```json
[
  {
    "id": "evt-01hzv4k8m3n7p2q5r8s0t6w9",
    "type": "task.completed",
    "timestamp": "2026-03-13T10:30:00Z",
    "ledger_version": 42,
    "proposal_id": null,
    "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
    "agent_id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
    "payload": { "verdict": "pass" },
    "source": "evaluation-engine",
    "idempotency_key": "eval-task-01hzv4-1"
  }
]
```

**Supported EventType values:**

`ledger.updated`, `proposal.created`, `proposal.accepted`, `proposal.rejected`, `task.created`, `task.started`, `task.completed`, `task.failed`, `task.retried`, `agent.spawned`, `agent.heartbeat`, `agent.completed`, `agent.failed`, `sandbox.created`, `sandbox.command`, `sandbox.destroyed`, `eval.started`, `eval.layer_completed`, `eval.completed`, `budget.warning`, `budget.exhausted`

---

## 2. Task Graph Engine API (Port 8003)

The Task Graph Engine decomposes specifications into a DAG of tasks, determines execution order via topological sort, and tracks task lifecycle. Orchestration is handled by Temporal workflows behind the scenes.

### POST /tasks/submit

Submit a project specification for decomposition and execution. The engine breaks the spec into individual tasks (implement, test, review triplets per module), builds a dependency DAG, and returns the task list with execution order.

**Request Body:**

```json
{
  "spec": {
    "title": "User Authentication Module",
    "description": "Implement JWT-based authentication with login, logout, and token refresh.",
    "modules": [
      {
        "name": "auth_service",
        "description": "Core authentication logic with JWT token management.",
        "priority": 10,
        "acceptance_criteria": [
          "Login endpoint returns JWT on valid credentials",
          "Token refresh extends session without re-authentication",
          "Logout invalidates the current token"
        ]
      },
      {
        "name": "auth_middleware",
        "description": "FastAPI middleware that validates JWT on protected routes.",
        "priority": 5,
        "acceptance_criteria": [
          "Returns 401 for missing or invalid tokens",
          "Injects user context into request state"
        ]
      }
    ]
  }
}
```

| Field                                  | Type   | Required | Description                                |
|----------------------------------------|--------|----------|--------------------------------------------|
| spec.title                             | string | yes      | Project/feature title                      |
| spec.description                       | string | yes      | Detailed description of the work           |
| spec.modules                           | array  | yes      | List of modules to decompose               |
| spec.modules[].name                    | string | yes      | Module name                                |
| spec.modules[].description             | string | yes      | What this module does                      |
| spec.modules[].priority                | int    | no       | Priority weight (higher = more important)  |
| spec.modules[].acceptance_criteria     | array  | no       | List of acceptance criteria strings        |

**Response** (201 Created):

```json
{
  "tasks": [
    {
      "id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
      "type": "implement_feature",
      "agent_type": "coder",
      "model_tier": "tier_2",
      "dependencies": [],
      "dependents": ["task-02abc..."],
      "budget": {
        "max_tokens": 100000,
        "max_time": "PT30M",
        "max_retries": 3,
        "max_output_size_bytes": 1000000
      },
      "status": "pending",
      "priority": 10,
      "description": "Implement auth_service module"
    }
  ],
  "execution_order": [
    "task-01hzv4k8m3n7p2q5r8s0t6w9",
    "task-02abc...",
    "task-03def..."
  ]
}
```

### GET /tasks/{task_id}

Retrieve full details for a single task, including retry history and timestamps.

**Path Parameters:**

| Name    | Type   | Required | Description |
|---------|--------|----------|-------------|
| task_id | string | yes      | Task ID     |

**Response** (200 OK):

```json
{
  "id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "type": "implement_feature",
  "agent_type": "coder",
  "model_tier": "tier_2",
  "dependencies": [],
  "dependents": ["task-02abc..."],
  "inputs": [],
  "outputs": [
    {
      "key": "source_code",
      "artifact_uri": "s3://architect/artifacts/task-01hzv4.../src.tar.gz",
      "content_hash": "sha256:abc123...",
      "size_bytes": 4096
    }
  ],
  "budget": {
    "max_tokens": 100000,
    "max_time": "PT30M",
    "max_retries": 3,
    "max_output_size_bytes": 1000000
  },
  "status": "completed",
  "assigned_agent": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "priority": 10,
  "timestamps": {
    "created_at": "2026-03-13T10:00:00Z",
    "started_at": "2026-03-13T10:01:00Z",
    "completed_at": "2026-03-13T10:12:00Z"
  },
  "current_attempt": 1,
  "retry_history": [
    {
      "attempt": 1,
      "started_at": "2026-03-13T10:01:00Z",
      "ended_at": "2026-03-13T10:12:00Z",
      "verdict": "pass",
      "failure_reason": null,
      "tokens_consumed": 45200
    }
  ],
  "verdict": "pass",
  "error_message": null,
  "description": "Implement auth_service module"
}
```

**Errors:**

| Status | Condition      |
|--------|----------------|
| 404    | Task not found |

### GET /tasks

List tasks with optional filtering.

**Query Parameters:**

| Name   | Type   | Default | Description                                                         |
|--------|--------|---------|---------------------------------------------------------------------|
| status | string | (none)  | Filter by StatusEnum: `pending`, `running`, `completed`, `failed`, `blocked`, `cancelled` |
| type   | string | (none)  | Filter by TaskType: `implement_feature`, `write_test`, `review_code`, `fix_bug`, `refactor` |

**Response** (200 OK):

```json
[
  {
    "id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
    "type": "implement_feature",
    "status": "completed",
    "priority": 10,
    "description": "Implement auth_service module",
    "assigned_agent": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
    "verdict": "pass"
  }
]
```

### GET /graph

Get the current task graph state including all tasks and the computed execution order.

**Response** (200 OK):

```json
{
  "tasks": [ ... ],
  "execution_order": [
    "task-01hzv4k8m3n7p2q5r8s0t6w9",
    "task-02abc...",
    "task-03def..."
  ],
  "created_at": "2026-03-13T10:00:00Z"
}
```

---

## 3. Execution Sandbox API (Port 8007)

The Execution Sandbox provides isolated Docker containers for running generated code. Each sandbox session is associated with a task and agent, has strict resource limits, and produces a full audit trail.

### POST /sandbox/create

Create a new sandbox container. The container starts from a base image with a read-only root filesystem, tmpfs `/tmp`, and runs as a non-root user.

**Request Body:**

```json
{
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "agent_id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "base_image": "architect-sandbox:latest",
  "resource_limits": {
    "cpu_cores": 2,
    "memory_mb": 4096,
    "disk_mb": 10240,
    "timeout_seconds": 900
  },
  "network_policy": {
    "allow_egress": false,
    "allowed_hosts": []
  }
}
```

| Field                               | Type   | Required | Default                      | Description                            |
|-------------------------------------|--------|----------|------------------------------|----------------------------------------|
| task_id                             | string | yes      | --                           | Task this sandbox is for               |
| agent_id                            | string | yes      | --                           | Agent that requested the sandbox       |
| base_image                          | string | no       | `architect-sandbox:latest`   | Docker image to use                    |
| resource_limits.cpu_cores           | int    | no       | 2                            | CPU core limit (1-8)                   |
| resource_limits.memory_mb           | int    | no       | 4096                         | Memory limit in MB (256-16384)         |
| resource_limits.disk_mb             | int    | no       | 10240                        | Disk limit in MB (1024-51200)          |
| resource_limits.timeout_seconds     | int    | no       | 900                          | Maximum session duration (10-3600)     |
| network_policy.allow_egress         | bool   | no       | false                        | Whether to allow outbound network      |
| network_policy.allowed_hosts        | array  | no       | []                           | Allowlisted hostnames if egress on     |

**Response** (201 Created):

```json
{
  "id": "sbx-01hzv4k8m3n7p2q5r8s0t6w9",
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "agent_id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "status": "ready",
  "container_id": "a1b2c3d4e5f6...",
  "image": "architect-sandbox:latest",
  "resource_limits": {
    "cpu_cores": 2,
    "memory_mb": 4096,
    "disk_mb": 10240
  },
  "created_at": "2026-03-13T10:00:00Z",
  "timeout_seconds": 900
}
```

### POST /sandbox/{session_id}/exec

Execute a command inside the sandbox. All commands are logged to the audit trail.

**Path Parameters:**

| Name       | Type   | Required | Description       |
|------------|--------|----------|-------------------|
| session_id | string | yes      | Sandbox session ID |

**Request Body:**

```json
{
  "command": "cd /workspace && python -m pytest --tb=short -q",
  "timeout": 300
}
```

| Field   | Type   | Required | Default | Description                     |
|---------|--------|----------|---------|---------------------------------|
| command | string | yes      | --      | Shell command to execute        |
| timeout | int    | no       | 60      | Per-command timeout in seconds  |

**Response** (200 OK):

```json
{
  "exit_code": 0,
  "stdout": "5 passed in 1.23s\n",
  "stderr": ""
}
```

**Errors:**

| Status | Condition                                          |
|--------|----------------------------------------------------|
| 403    | Command matches a blocked pattern (e.g., `rm -rf /`, `curl`, `wget`) |
| 408    | Command exceeded the timeout                       |
| 404    | Session not found                                  |

### POST /sandbox/{session_id}/files

Write files into the sandbox workspace. Files are transferred via tar archives internally.

**Path Parameters:**

| Name       | Type   | Required | Description       |
|------------|--------|----------|-------------------|
| session_id | string | yes      | Sandbox session ID |

**Request Body:**

```json
{
  "files": {
    "src/auth_service.py": "\"\"\"Authentication service.\"\"\"\n\nimport jwt\n...",
    "tests/test_auth.py": "\"\"\"Tests for auth_service.\"\"\"\n\nimport pytest\n..."
  }
}
```

| Field | Type              | Required | Description                          |
|-------|-------------------|----------|--------------------------------------|
| files | object (path->str)| yes      | Mapping of file path to file content |

**Response:** 204 No Content

### GET /sandbox/{session_id}/files

Read files from the sandbox workspace.

**Path Parameters:**

| Name       | Type   | Required | Description       |
|------------|--------|----------|-------------------|
| session_id | string | yes      | Sandbox session ID |

**Query Parameters:**

| Name  | Type   | Required | Description                                   |
|-------|--------|----------|-----------------------------------------------|
| paths | string | yes      | Comma-separated list of file paths to read    |

**Example:** `GET /sandbox/sbx-01.../files?paths=src/auth_service.py,tests/test_auth.py`

**Response** (200 OK):

```json
{
  "files": {
    "src/auth_service.py": "\"\"\"Authentication service.\"\"\"\n\nimport jwt\n...",
    "tests/test_auth.py": "\"\"\"Tests for auth_service.\"\"\"\n\nimport pytest\n..."
  }
}
```

### DELETE /sandbox/{session_id}

Destroy the sandbox container and reclaim all resources. The container is stopped and removed, but the audit log is preserved.

**Path Parameters:**

| Name       | Type   | Required | Description       |
|------------|--------|----------|-------------------|
| session_id | string | yes      | Sandbox session ID |

**Response:** 204 No Content

---

## 4. Evaluation Engine API (Port 8008)

The Evaluation Engine runs a multi-layer evaluation pipeline against code in a sandbox. In Phase 1, the pipeline consists of a Compilation layer and a Unit Test layer. The engine uses a pluggable architecture, so additional layers are added in later phases.

### POST /evaluate

Run the full evaluation pipeline for a task. The engine executes each evaluation layer sequentially within the sandbox. If any layer returns `FAIL_HARD`, the pipeline stops immediately (fail-fast mode).

**Request Body:**

```json
{
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "sandbox_session_id": "sbx-01hzv4k8m3n7p2q5r8s0t6w9"
}
```

| Field              | Type   | Required | Description                            |
|--------------------|--------|----------|----------------------------------------|
| task_id            | string | yes      | Task being evaluated                   |
| sandbox_session_id | string | yes      | Active sandbox session with code to evaluate |

**Response** (200 OK):

```json
{
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "layers": [
    {
      "layer": "compilation",
      "verdict": "pass",
      "details": {
        "success": true,
        "errors": [],
        "warnings": [],
        "duration_seconds": 2.3
      },
      "started_at": "2026-03-13T10:05:00Z",
      "completed_at": "2026-03-13T10:05:02Z"
    },
    {
      "layer": "unit_tests",
      "verdict": "pass",
      "details": {
        "total": 12,
        "passed": 12,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration_seconds": 4.5,
        "failure_details": []
      },
      "started_at": "2026-03-13T10:05:02Z",
      "completed_at": "2026-03-13T10:05:07Z"
    }
  ],
  "overall_verdict": "pass",
  "created_at": "2026-03-13T10:05:00Z"
}
```

**Verdict semantics:**

| Verdict     | Meaning                                                            |
|-------------|--------------------------------------------------------------------|
| `pass`      | All checks passed; code is ready to commit                        |
| `fail_soft` | Some tests failed but the code compiles; retryable by the agent   |
| `fail_hard` | Fatal error (e.g., syntax error, import failure); stops pipeline  |

**Phase 1 evaluation layers (executed in order):**

1. **Compilation** -- Runs `python -m py_compile` on all `.py` files. Returns `pass` or `fail_hard`.
2. **Unit Tests** -- Runs `pytest --tb=short -q`. Returns `pass`, `fail_soft` (test failures), or `fail_hard` (collection/import errors).

### GET /reports/{task_id}

Retrieve the evaluation report for a specific task.

**Path Parameters:**

| Name    | Type   | Required | Description             |
|---------|--------|----------|-------------------------|
| task_id | string | yes      | Task ID to look up      |

**Response** (200 OK):

Same schema as the `POST /evaluate` response.

**Errors:**

| Status | Condition                       |
|--------|---------------------------------|
| 404    | No evaluation report for this task |

---

## 5. Coding Agent API (Port 8009)

The Coding Agent executes an LLM-driven code generation loop: plan the implementation, generate code, write to sandbox, run tests, and iterate on failures. It uses the Anthropic Claude API through the shared `architect-llm` client library.

### POST /agent/execute

Execute the coding agent on a task. The agent loop follows these steps:
1. **Plan** -- Generate an implementation plan from the specification.
2. **Generate** -- Produce code files via LLM, parsed from fenced code blocks.
3. **Test** -- Write files to sandbox and run compilation + tests.
4. **Iterate** -- If tests fail, send error context back to the LLM for fixes (up to `max_retries`).
5. **Return** -- Produce the final output with all generated files and metadata.

**Request Body:**

```json
{
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "spec": {
    "title": "User Authentication Service",
    "description": "Implement JWT-based authentication with login, logout, and token refresh.",
    "acceptance_criteria": [
      "Login endpoint returns JWT on valid credentials",
      "Token refresh extends session without re-authentication"
    ],
    "constraints": [
      "Use PyJWT library",
      "Tokens expire after 1 hour"
    ]
  },
  "codebase_context": {
    "relevant_files": ["src/models/user.py", "src/config.py"],
    "file_contents": {
      "src/models/user.py": "from pydantic import BaseModel\n\nclass User(BaseModel):\n    ...",
      "src/config.py": "JWT_SECRET = 'dev-secret'\n..."
    }
  },
  "config": {
    "model_tier": "tier_2",
    "temperature": 0.2
  }
}
```

| Field                              | Type    | Required | Default              | Description                                |
|------------------------------------|---------|----------|----------------------|--------------------------------------------|
| task_id                            | string  | yes      | --                   | Task to execute                            |
| spec.title                         | string  | yes      | --                   | Task title                                 |
| spec.description                   | string  | no       | ""                   | Detailed description                       |
| spec.acceptance_criteria           | array   | no       | []                   | List of acceptance criteria                |
| spec.constraints                   | array   | no       | []                   | Implementation constraints                 |
| codebase_context.relevant_files    | array   | no       | []                   | File paths for context                     |
| codebase_context.file_contents     | object  | no       | {}                   | File path to content mapping               |
| config.model_tier                  | string  | no       | `tier_2`             | LLM tier to use                            |
| config.temperature                 | float   | no       | 0.2                  | LLM sampling temperature (0.0-1.0)        |

**Response** (200 OK):

```json
{
  "agent_id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "status": "completed",
  "output": {
    "files": [
      {
        "path": "src/auth_service.py",
        "content": "\"\"\"Authentication service.\"\"\"\n\nimport jwt\n...",
        "is_test": false
      },
      {
        "path": "tests/test_auth_service.py",
        "content": "\"\"\"Tests for auth_service.\"\"\"\n\nimport pytest\n...",
        "is_test": true
      }
    ],
    "commit_message": "feat: implement User Authentication Service\n\nGenerated 1 source file(s) and 1 test file(s)\nTask: task-01hzv4k8m3n7p2q5r8s0t6w9\nAgent: agent-01hzv4k8m3n7p2q5r8s0t6w9",
    "reasoning_summary": "The implementation uses PyJWT for token management. Login validates credentials against the user store and returns a signed JWT...",
    "tokens_used": 45200
  }
}
```

### GET /agent/{agent_id}

Get the status and output of a coding agent run.

**Path Parameters:**

| Name     | Type   | Required | Description  |
|----------|--------|----------|--------------|
| agent_id | string | yes      | Agent run ID |

**Response** (200 OK):

```json
{
  "id": "agent-01hzv4k8m3n7p2q5r8s0t6w9",
  "task_id": "task-01hzv4k8m3n7p2q5r8s0t6w9",
  "config": {
    "agent_type": "coder",
    "model_tier": "tier_2",
    "model_id": "claude-sonnet-4-20250514",
    "max_context_tokens": 180000,
    "max_output_tokens": 16000,
    "temperature": 0.2,
    "system_prompt": ""
  },
  "status": "completed",
  "spec_context": { ... },
  "codebase_context": { ... },
  "output": { ... },
  "started_at": "2026-03-13T10:01:00Z",
  "completed_at": "2026-03-13T10:12:00Z",
  "error": null
}
```

**Errors:**

| Status | Condition           |
|--------|---------------------|
| 404    | Agent run not found |

---

## 6. Spec Engine (Port 8010)

### `POST /api/v1/specs` -- Create Specification

Submit a natural-language task description for parsing into a formal spec.

**Request body:**

```json
{
  "raw_text": "Build an OAuth2 login flow with Google that completes in under 2 seconds"
}
```

**Response (200):**

```json
{
  "spec": {
    "id": "spec-a1b2c3d4e5f6",
    "intent": "Implement OAuth2 login with Google provider",
    "constraints": ["Must complete in under 2 seconds", "Must support PKCE flow"],
    "success_criteria": [
      {
        "id": "ac-1a2b3c4d",
        "description": "OAuth2 login with Google completes in < 2s",
        "test_type": "integration",
        "automated": true
      }
    ],
    "file_targets": ["src/auth/oauth.py", "src/auth/providers/google.py"],
    "assumptions": ["PostgreSQL is the primary datastore"],
    "open_questions": [],
    "created_at": "2026-03-14T12:00:00Z"
  },
  "needs_clarification": false,
  "questions": []
}
```

If the input is ambiguous, `needs_clarification` is `true` and `spec` is `null`:

```json
{
  "spec": null,
  "needs_clarification": true,
  "questions": [
    {
      "question": "Which OAuth2 provider should be used?",
      "context": "The description mentions login but not the identity provider",
      "priority": "high"
    }
  ]
}
```

### `GET /api/v1/specs/{spec_id}` -- Get Specification

**Response (200):** Returns the stored `SpecResult` for the given ID.

**Errors:**

| Status | Condition |
|--------|-----------|
| 404    | Spec not found |

### `POST /api/v1/specs/{spec_id}/clarify` -- Answer Clarifications

**Request body:**

```json
{
  "answers": {
    "Which OAuth2 provider should be used?": "Google"
  }
}
```

**Response (200):** Returns an updated `SpecResult` (may still need further clarification).

---

## 7. Multi-Model Router (Port 8011)

### `POST /api/v1/route` -- Get Routing Decision

**Request body:**

```json
{
  "task_id": "task-abc123",
  "task_type": "implement_feature",
  "description": "Add rate limiting middleware to the API gateway",
  "token_estimate": 50000,
  "keywords": ["middleware", "security"]
}
```

**Response (200):**

```json
{
  "decision": {
    "task_id": "task-abc123",
    "selected_tier": "tier_2",
    "model_id": "claude-sonnet-4-20250514",
    "complexity": {
      "score": 0.55,
      "factors": {
        "task_type": 0.5,
        "token_estimate": 0.5,
        "description": 0.4,
        "keywords": 0.7
      },
      "recommended_tier": "tier_2"
    },
    "override_reason": null,
    "timestamp": "2026-03-14T12:00:00Z"
  }
}
```

### `GET /api/v1/route/stats` -- Routing Statistics

**Response (200):**

```json
{
  "total_requests": 142,
  "tier_distribution": { "tier_1": 12, "tier_2": 85, "tier_3": 45 },
  "escalation_count": 7,
  "average_complexity": 0.43
}
```

---

## 8. Codebase Comprehension (Port 8012)

### `POST /api/v1/index` -- Index a Directory

**Request body:**

```json
{
  "directory": "/path/to/project",
  "glob_pattern": "**/*.py"
}
```

**Response (200):**

```json
{
  "root_path": "/path/to/project",
  "total_files": 47,
  "total_symbols": 312,
  "indexed_at": "2026-03-14T12:00:00Z"
}
```

### `GET /api/v1/context` -- Get Code Context

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_description` | string | Natural-language description of the task |

**Response (200):**

```json
{
  "relevant_files": ["src/auth/oauth.py", "src/middleware/rate_limit.py"],
  "file_chunks": {
    "src/auth/oauth.py": "class OAuthProvider:\n    ..."
  },
  "related_symbols": [
    {
      "name": "OAuthProvider",
      "kind": "class",
      "file_path": "src/auth/oauth.py",
      "line_number": 15,
      "docstring": "Base OAuth2 provider."
    }
  ],
  "related_tests": ["tests/test_auth.py"],
  "import_graph": {
    "src/auth/oauth.py": ["src/auth/providers/base.py"]
  }
}
```

### `GET /api/v1/symbols` -- Search Symbols

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | | Case-insensitive substring match |
| `limit` | int | 20 | Max results to return |

**Response (200):** Array of `SymbolInfo` objects.

### `POST /api/v1/index/embed` -- Generate Embeddings

Generate vector embeddings for an indexed codebase and store them in pgvector for semantic search.

**Request body:**

```json
{
  "directory": "/path/to/project",
  "database_url": "postgresql+asyncpg://architect:$ARCHITECT_PG_PASSWORD@localhost:5432/architect"
}
```

**Response (200):**

```json
{
  "root_path": "/path/to/project",
  "total_chunks": 156,
  "total_embeddings": 156
}
```

### `GET /api/v1/context/semantic` -- Semantic Search

Search for code using semantic similarity via pgvector embeddings.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | | Natural-language search query |
| `root_path` | string | (none) | Filter results to a specific codebase |
| `limit` | int | 20 | Max results to return |

**Response (200):**

```json
{
  "results": [
    {
      "symbol_name": "OAuthProvider",
      "symbol_kind": "class",
      "file_path": "src/auth/oauth.py",
      "line_number": 15,
      "source_chunk": "class OAuthProvider:\n    ...",
      "score": 0.87,
      "metadata": {}
    }
  ],
  "total": 1
}
```

---

## 9. Agent Communication Bus (Port 8013)

### `GET /api/v1/bus/stats` -- Bus Statistics

**Response (200):**

```json
{
  "total_published": 1523,
  "total_received": 1519,
  "by_type": {
    "task.assigned": 200,
    "task.completed": 185,
    "context.request": 450,
    "context.response": 448
  },
  "dead_letter_count": 4,
  "active_subscriptions": 12
}
```

### `POST /api/v1/bus/publish` -- Publish Message

**Request body:**

```json
{
  "sender": "agent-abc123",
  "recipient": "agent-def456",
  "message_type": "context.request",
  "payload": {
    "task_id": "task-xyz789",
    "context_type": "codebase"
  },
  "correlation_id": "corr-111222"
}
```

**Response (200):**

```json
{
  "status": "published",
  "message_id": "msg-a1b2c3d4e5f6"
}
```

### `GET /api/v1/bus/health` -- Bus Health

**Response (200):**

```json
{
  "status": "healthy",
  "nats_connected": true,
  "stream_name": "ARCHITECT"
}
```

---

## 10. Knowledge & Memory (Port 8014)

The Knowledge & Memory service manages long-term knowledge storage, working memory for active tasks, heuristic rules evolved from past observations, and a compression pipeline that distills raw data into reusable patterns and strategies.

### `POST /api/v1/knowledge/query` -- Search Knowledge

Search knowledge entries by semantic similarity and metadata filters.

**Request body:**

```json
{
  "layer": "domain",
  "topic": "authentication",
  "content_type": "documentation",
  "limit": 20
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| layer | string | no | Filter by knowledge layer |
| topic | string | no | Filter by topic |
| content_type | string | no | Filter by content type (e.g., `documentation`, `pattern`) |
| limit | int | no | Maximum results to return |

**Response (200):**

```json
{
  "entries": [
    {
      "id": "know-abc123",
      "layer": "domain",
      "topic": "authentication",
      "title": "JWT Token Refresh Patterns",
      "content": "...",
      "content_type": "documentation",
      "confidence": 0.92,
      "tags": ["jwt", "auth"],
      "source": "doc_fetcher",
      "usage_count": 5,
      "active": true
    }
  ],
  "total": 1
}
```

### `GET /api/v1/knowledge/{knowledge_id}` -- Get Knowledge Entry

Retrieve a specific knowledge entry by ID. Increments the usage counter on each access.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| knowledge_id | string | yes | Knowledge entry ID |

**Response (200):** Full knowledge entry object.

**Errors:**

| Status | Condition |
|--------|-----------|
| 404 | Knowledge entry not found |

### `POST /api/v1/knowledge` -- Create Knowledge Entry

Store a new knowledge entry.

**Request body:** A `KnowledgeEntry` object with fields: `id`, `layer`, `topic`, `title`, `content`, `content_type`, `confidence`, `tags`, `embedding`, `version_tag`, `source`.

**Response (201):**

```json
{
  "id": "know-abc123",
  "status": "created"
}
```

### `PUT /api/v1/knowledge/{knowledge_id}/feedback` -- Provide Feedback

Provide feedback on a knowledge entry. Positive feedback increments usage; negative feedback deactivates the entry.

**Request body:**

```json
{
  "useful": true
}
```

**Response (200):**

```json
{
  "id": "know-abc123",
  "status": "feedback_recorded"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| 404 | Knowledge entry not found |

### `GET /api/v1/heuristics` -- List Heuristics

List all active heuristic rules with optional domain filter.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| domain | string | (none) | Filter heuristics by domain |

**Response (200):** Array of heuristic rule objects.

### `GET /api/v1/heuristics/match` -- Match Heuristics

Find heuristics matching the given task type and domain criteria.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| task_type | string | (none) | Filter by task type |
| domain | string | (none) | Filter by domain |

**Response (200):** Array of matching heuristic rule objects.

### `POST /api/v1/heuristics/{heuristic_id}/outcome` -- Record Outcome

Record a success or failure outcome for a heuristic, triggering confidence evolution.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| heuristic_id | string | yes | Heuristic rule ID |

**Request body:**

```json
{
  "success": true
}
```

**Response (200):**

```json
{
  "id": "heur-abc123",
  "status": "outcome_recorded"
}
```

### `POST /api/v1/acquire` -- Trigger Knowledge Acquisition

Trigger an asynchronous knowledge acquisition workflow. In production, this starts a Temporal workflow.

**Request body:**

```json
{
  "topic": "oauth2",
  "source_urls": ["https://example.com/docs/oauth2"]
}
```

**Response (202):**

```json
{
  "status": "accepted",
  "topic": "oauth2",
  "message": "Knowledge acquisition workflow queued."
}
```

### `POST /api/v1/compress` -- Trigger Compression

Trigger the compression pipeline to distill observations into patterns, heuristics, and meta-strategies.

**Request body:**

```json
{
  "scope": "all"
}
```

**Response (200):**

```json
{
  "patterns_created": 0,
  "heuristics_created": 0,
  "strategies_proposed": 0,
  "observations_processed": 0
}
```

### `GET /api/v1/working-memory/{task_id}/{agent_id}` -- Get Working Memory

Retrieve working memory for a specific task-agent pair.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| task_id | string | yes | Task ID |
| agent_id | string | yes | Agent ID |

**Response (200):** Working memory object with `scratchpad`, `context_entries`, and metadata.

**Errors:**

| Status | Condition |
|--------|-----------|
| 404 | Working memory not found for this task-agent pair |

### `POST /api/v1/working-memory/{task_id}/{agent_id}` -- Update Working Memory

Create or update working memory for a task-agent pair.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| task_id | string | yes | Task ID |
| agent_id | string | yes | Agent ID |

**Request body:**

```json
{
  "scratchpad_updates": { "current_step": "testing" },
  "add_context_entries": ["know-abc123"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| scratchpad_updates | object | no | Key-value pairs to merge into the scratchpad |
| add_context_entries | array of string | no | Knowledge entry IDs to add to context |

**Response (200):** Updated working memory object.

### `GET /api/v1/stats` -- Knowledge Store Statistics

Return aggregate statistics about the knowledge store.

**Response (200):**

```json
{
  "total_entries": 150,
  "entries_by_layer": { "domain": 80, "meta": 40, "operational": 30 },
  "total_observations": 500,
  "total_heuristics": 25,
  "total_meta_strategies": 3
}
```

### `GET /api/v1/meta-strategies` -- List Meta-Strategies

List all meta-strategies derived from the compression pipeline.

**Response (200):** Array of meta-strategy objects.

---

## 11. Economic Governor (Port 8015)

The Economic Governor tracks token and cost budgets, computes agent efficiency scores, and enforces spending limits via a tiered alert/restrict/halt model.

### `GET /api/v1/budget/status` -- Budget Snapshot

Return the current budget snapshot including total budget, consumed amounts, and enforcement level.

**Response (200):**

```json
{
  "total_budget_usd": 500.0,
  "consumed_usd": 125.50,
  "consumed_tokens": 2500000,
  "consumed_pct": 25.1,
  "enforcement_level": "normal",
  "phase_breakdown": [
    {
      "phase": "implementation",
      "allocated_usd": 200.0,
      "consumed_usd": 75.30
    }
  ]
}
```

### `GET /api/v1/budget/phases` -- Per-Phase Budget Breakdown

Return per-phase budget allocation and consumption.

**Response (200):** Array of `PhaseStatus` objects from the budget snapshot's `phase_breakdown`.

### `POST /api/v1/budget/allocate` -- Allocate Budget

Compute a budget allocation for a project.

**Request body:** A `BudgetAllocationRequest` object with project parameters.

**Response (200):**

```json
{
  "total_usd": 500.0,
  "phases": [
    { "phase": "implementation", "allocated_usd": 200.0 },
    { "phase": "testing", "allocated_usd": 150.0 }
  ]
}
```

### `POST /api/v1/budget/record-consumption` -- Record Token Consumption

Record token consumption for an agent and return the current enforcement level.

**Request body:**

```json
{
  "agent_id": "agent-abc123",
  "tokens": 5000,
  "cost_usd": 0.15
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| agent_id | string | yes | Agent that consumed tokens |
| tokens | int | yes | Number of tokens consumed (>= 0) |
| cost_usd | float | yes | Cost in USD (>= 0.0) |

**Response (200):**

```json
{
  "enforcement_level": "normal"
}
```

**Enforcement levels:** `normal`, `alert`, `restrict`, `halt`

### `GET /api/v1/efficiency/leaderboard` -- Agent Efficiency Leaderboard

Return the agent efficiency leaderboard with scores for all tracked agents.

**Response (200):**

```json
{
  "entries": [
    {
      "agent_id": "agent-abc123",
      "score": 0.85,
      "tokens_used": 50000,
      "tasks_completed": 10,
      "cost_per_task": 1.50
    }
  ],
  "computed_at": "2026-03-14T12:00:00Z"
}
```

### `GET /api/v1/efficiency/agent/{agent_id}` -- Agent Efficiency Score

Return the efficiency score for a specific agent.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| agent_id | string | yes | Agent ID |

**Response (200):** A single `AgentEfficiencyScore` object.

### `GET /api/v1/enforcement/history` -- Enforcement Action History

Return the history of enforcement actions (level transitions, warnings, restrictions).

**Response (200):** Array of `EnforcementRecord` objects.

### `GET /api/v1/enforcement/current-level` -- Current Enforcement Level

Return the current enforcement level and budget consumption percentage.

**Response (200):**

```json
{
  "level": "normal",
  "consumed_pct": 25.1
}
```

---

## 12. Human Interface (Port 8016)

The Human Interface service manages escalations (decisions requiring human input), approval gates (multi-party sign-off), progress aggregation, activity feeds, and real-time WebSocket push to the dashboard.

### `POST /api/v1/escalations` -- Create Escalation

Create a new escalation and broadcast to connected WebSocket clients.

**Request body:**

```json
{
  "source_agent_id": "agent-abc123",
  "source_task_id": "task-xyz789",
  "summary": "Ambiguous requirement: authentication method unclear",
  "category": "ambiguity",
  "severity": "high",
  "options": [
    { "label": "Use OAuth2", "description": "Implement OAuth2 with Google" },
    { "label": "Use API keys", "description": "Implement API key auth" }
  ],
  "recommended_option": 0,
  "reasoning": "OAuth2 is mentioned in related docs",
  "risk_if_wrong": "Wrong auth implementation requires full rewrite",
  "expires_in_minutes": 60
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| source_agent_id | string | yes | Agent raising the escalation |
| source_task_id | string | yes | Related task |
| summary | string | yes | Human-readable summary |
| category | EscalationCategory | yes | Category enum value |
| severity | EscalationSeverity | yes | Severity enum value |
| options | array | no | Decision options |
| recommended_option | int | no | Index of recommended option |
| reasoning | string | no | Agent's reasoning |
| risk_if_wrong | string | no | Risk assessment |
| expires_in_minutes | int | no | Auto-expire timeout (default from config) |

**Response (201):** Full `EscalationResponse` object.

### `GET /api/v1/escalations` -- List Escalations

List escalations with optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | EscalationStatus | (none) | Filter by status: `pending`, `resolved`, `expired`, `auto_resolved` |
| category | EscalationCategory | (none) | Filter by category |
| severity | EscalationSeverity | (none) | Filter by severity |
| limit | int | 50 | Maximum results (1-1000) |
| offset | int | 0 | Pagination offset |

**Response (200):** Array of `EscalationResponse` objects.

### `GET /api/v1/escalations/stats` -- Escalation Statistics

Return aggregated escalation statistics.

**Response (200):**

```json
{
  "total": 42,
  "pending": 5,
  "resolved": 30,
  "expired": 7
}
```

### `GET /api/v1/escalations/{escalation_id}` -- Get Escalation

Get a single escalation by ID.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| escalation_id | string | yes | Escalation ID |

**Response (200):** Full `EscalationResponse` object.

**Errors:**

| Status | Condition |
|--------|-----------|
| 404 | Escalation not found |

### `POST /api/v1/escalations/{escalation_id}/resolve` -- Resolve Escalation

Resolve an escalation with a human decision. Identity is taken from the `X-Authenticated-User` header or the `resolved_by` request field.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| escalation_id | string | yes | Escalation to resolve |

**Request body:**

```json
{
  "resolved_by": "operator@example.com",
  "resolution": "Use OAuth2",
  "custom_input": { "provider": "google" }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| resolved_by | string | no | Resolver identity (fallback if no header) |
| resolution | string | yes | The chosen resolution |
| custom_input | object | no | Additional resolution context |

**Response (200):** Updated `EscalationResponse` object.

**Errors:**

| Status | Condition |
|--------|-----------|
| 401 | No identity provided (missing header and body field) |
| 404 | Escalation not found |

### `POST /api/v1/approval-gates` -- Create Approval Gate

Create a new approval gate requiring multi-party sign-off.

**Request body:**

```json
{
  "action_type": "deploy",
  "resource_id": "service-auth-v2",
  "required_approvals": 2,
  "context": { "environment": "production" },
  "expires_in_minutes": 120
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| action_type | string | yes | Type of action requiring approval |
| resource_id | string | yes | Resource being acted upon |
| required_approvals | int | yes | Number of approvals needed |
| context | object | no | Additional context |
| expires_in_minutes | int | no | Auto-expire timeout |

**Response (201):** Full `ApprovalGateResponse` object.

### `GET /api/v1/approval-gates` -- List Approval Gates

List approval gates with optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | ApprovalGateStatus | (none) | Filter: `pending`, `approved`, `denied`, `expired` |
| action_type | string | (none) | Filter by action type |
| limit | int | 50 | Maximum results (1-1000) |
| offset | int | 0 | Pagination offset |

**Response (200):** Array of `ApprovalGateResponse` objects.

### `GET /api/v1/approval-gates/{gate_id}` -- Get Approval Gate

Get a single approval gate by ID.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| gate_id | string | yes | Approval gate ID |

**Response (200):** Full `ApprovalGateResponse` object.

**Errors:**

| Status | Condition |
|--------|-----------|
| 404 | Approval gate not found |

### `POST /api/v1/approval-gates/{gate_id}/vote` -- Cast Vote

Cast a vote on an approval gate. Auto-resolves when enough votes are reached. A "deny" vote immediately denies the gate. Identity is taken from `X-Authenticated-User` header or `voter` request field.

**Path parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| gate_id | string | yes | Approval gate ID |

**Request body:**

```json
{
  "voter": "operator@example.com",
  "decision": "approve",
  "comment": "Looks good to deploy"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| voter | string | no | Voter identity (fallback if no header) |
| decision | string | yes | `approve` or `deny` |
| comment | string | no | Optional comment |

**Response (200):** Updated `ApprovalGateResponse` object.

**Errors:**

| Status | Condition |
|--------|-----------|
| 400 | Gate is no longer pending |
| 401 | No identity provided |
| 404 | Approval gate not found |
| 409 | Voter has already voted on this gate |

### `GET /api/v1/progress` -- Progress Summary

Aggregate progress from task graph and budget services. Falls back to defaults if upstream services are unavailable.

**Response (200):**

```json
{
  "tasks_completed": 15,
  "tasks_total": 42,
  "completion_pct": 35.7,
  "budget_consumed_pct": 25.1
}
```

### `GET /api/v1/activity` -- Activity Feed

Return recent activity events (stub -- returns empty list in current implementation).

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 20 | Maximum results (1-200) |

**Response (200):** Array of `ActivityEvent` objects.

### `WebSocket /api/v1/ws` -- Real-Time Push

WebSocket endpoint for real-time event push to dashboard clients. See [WebSocket Protocol Specification](websocket-protocol.md) for full details.

**Connection:** `ws://host:8016/api/v1/ws?token=<ARCHITECT_WS_TOKEN>`

**Authentication:** Token-based via query parameter, validated against `ARCHITECT_WS_TOKEN` env var.

**Broadcast message types:** `escalation_created`, `escalation_resolved`, `approval_gate_created`, `approval_vote_cast`
