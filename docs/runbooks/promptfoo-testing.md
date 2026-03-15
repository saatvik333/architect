# PromptFoo Testing

Guide for running and maintaining LLM prompt regression tests in the ARCHITECT project.

---

## Overview

ARCHITECT uses [PromptFoo](https://www.promptfoo.dev/) to prevent prompt regressions. When you modify an LLM prompt used by any service (Spec Engine, Coding Agent, Evaluation Engine), these tests verify that the model still produces structurally correct output -- valid JSON schemas, expected fields, security-aware responses, and so on.

Tests live in `promptfoo/suites/` and are coordinated by `promptfoo/promptfooconfig.yaml`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Bun 1.0+ | Package manager for PromptFoo (`bun --version`) |
| `ANTHROPIC_API_KEY` | Must be set in your environment; tests call the Claude API |

---

## Running Tests

### Run all suites

```bash
make promptfoo-test
```

This installs dependencies (`bun install`) and runs `promptfoo eval` against all four suites.

### View results in the browser

```bash
make promptfoo-view
```

Opens the PromptFoo web UI showing pass/fail details for each test case.

### Run a single suite

```bash
cd promptfoo
bun run test:suite suites/spec-parsing.yaml
```

Replace the path with any suite file under `promptfoo/suites/`.

---

## Test Suites

### `spec-parsing.yaml`

Tests the Spec Engine parser prompt. Verifies that clear requirements produce a structured spec (intent, constraints, success criteria, file targets) and that ambiguous inputs trigger clarification questions. Source: `services/spec-engine/src/spec_engine/parser.py`.

### `code-generation.yaml`

Tests the Coding Agent code generation and planning prompts. Verifies that the model produces syntactically plausible Python code for various task types: decorators, classes, async functions, and error handling. Source: `services/coding-agent/src/coding_agent/context_builder.py`.

### `adversarial-generation.yaml`

Tests the Evaluation Engine adversarial test generator. Given source code with deliberate vulnerabilities (null handling, SQL injection, path traversal, weak auth), verifies that the model generates pytest tests targeting those weaknesses. Source: `services/evaluation-engine/src/evaluation_engine/layers/adversarial.py`.

### `stakeholder-simulation.yaml`

Tests the Spec Engine stakeholder simulator and scope governor. Verifies that the model reviews specs from four personas (end user, security reviewer, product manager, ops engineer) and returns structured JSON with concerns, severity ratings, and an overall risk assessment. Source: `services/spec-engine/src/spec_engine/stakeholder_simulator.py`.

---

## Adding a New Suite

1. Create a new YAML file in `promptfoo/suites/`, e.g. `promptfoo/suites/my-feature.yaml`.
2. Follow the structure of existing suites: `description`, `providers`, `prompts`, `tests`, `defaultTest`, `scenarios`.
3. Reference the new file in `promptfoo/promptfooconfig.yaml` under the `prompts` list:

```yaml
prompts:
  - file://suites/spec-parsing.yaml
  - file://suites/code-generation.yaml
  - file://suites/adversarial-generation.yaml
  - file://suites/stakeholder-simulation.yaml
  - file://suites/my-feature.yaml
```

4. Run your new suite in isolation first to verify it passes before committing:

```bash
cd promptfoo && bun run test:suite suites/my-feature.yaml
```

---

## Provider Configuration

All suites use the same Anthropic provider. Settings are declared per-suite but should stay consistent:

| Setting | Value | Notes |
|---|---|---|
| Provider | `anthropic:messages:claude-sonnet-4-20250514` | Claude Sonnet 4 |
| `max_tokens` | 4000--4096 | Varies slightly by suite |
| `temperature` | 0.1--0.3 | Low values for deterministic output; adversarial/stakeholder suites use 0.3 |

To change the model globally, update the `providers` block in each suite YAML and in `promptfooconfig.yaml`.

---

## CI Note

PromptFoo tests are **not** included in CI by default. They require a valid `ANTHROPIC_API_KEY` and each run incurs API costs. Run them manually before merging changes that modify LLM prompts.
