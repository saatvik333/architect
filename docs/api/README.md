# ARCHITECT API Reference -- Phase 1 Services

This document covers the REST APIs exposed by the five Phase 1 services. All services are built on FastAPI, communicate via JSON request/response bodies, and follow shared conventions described below.

## General Conventions

### Base URL Pattern

Each service binds to a dedicated port on `localhost` during local development:

| Service              | Port |
|----------------------|------|
| World State Ledger   | 8001 |
| Execution Sandbox    | 8002 |
| Task Graph Engine    | 8003 |
| Evaluation Engine    | 8004 |
| Coding Agent         | 8009 |

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

## 3. Execution Sandbox API (Port 8002)

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

## 4. Evaluation Engine API (Port 8004)

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
