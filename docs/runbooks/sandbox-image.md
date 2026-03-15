# Sandbox Image

How to build, verify, and maintain the Docker image used by the Execution Sandbox service for isolated code execution.

---

## Overview

The `architect-sandbox` image provides a locked-down environment where ARCHITECT executes LLM-generated code. Each sandbox session runs inside a dedicated container created from this image. The image is intentionally minimal -- it contains only the tools needed to run Python code and install packages, with no unnecessary attack surface.

See [ADR-004](../architecture/adr/004-sandbox-strategy.md) for the full rationale behind Docker-based sandboxing.

---

## Building the Image

From the repository root:

```bash
docker build -f infra/dockerfiles/Dockerfile.sandbox -t architect-sandbox:latest .
```

No build arguments are required. The build is fully self-contained.

---

## Image Contents

The Dockerfile (`infra/dockerfiles/Dockerfile.sandbox`) installs the following on top of `python:3.12-slim`:

| Layer | Purpose |
|---|---|
| `git` | Clone repositories into `/workspace` |
| `build-essential` | Compile native Python extensions (C headers, gcc, make) |
| `curl`, `ca-certificates` | Download dependencies during package installation |
| `uv` (copied from `ghcr.io/astral-sh/uv:latest`) | Fast Python package management inside the sandbox |

A non-root user `sandbox` (UID/GID 1000) is created. The working directory is `/workspace`, owned by that user with 755 permissions. Environment variables disable Python bytecode caching and output buffering.

The entrypoint is `python3`. A healthcheck verifies the Python runtime starts correctly.

---

## Security Properties

Per ADR-004, containers created from this image are hardened at runtime by the Execution Sandbox service:

- **Non-root execution** -- the `USER sandbox` directive ensures all processes run as UID 1000.
- **Read-only root filesystem** -- the container root is mounted read-only; only `/workspace` (tmpfs) and `/tmp` are writable.
- **No network access** -- containers are created with `network_mode: none`.
- **Seccomp profile** -- a custom profile at `infra/seccomp/sandbox-profile.json` uses a default-deny policy, allowlisting only the syscalls Python needs while explicitly blocking `ptrace`, `mount`, `unshare`, `bpf`, and other dangerous calls.
- **Command validation** -- a `SecurityValidator` rejects privilege-escalation and escape attempts before execution.

---

## Resource Labels

The image carries OCI labels that declare default resource limits:

```
architect.resource.cpu=2
architect.resource.memory_mb=4096
architect.resource.disk_mb=10240
```

The Execution Sandbox service reads these labels (via `docker inspect`) when creating containers and maps them to Docker's `--cpus`, `--memory`, and tmpfs size options. Per-task overrides can lower these values but never exceed them.

---

## Verifying the Image

After building, confirm the image works correctly:

```bash
# Check Python version
docker run --rm architect-sandbox:latest --version

# Confirm non-root user
docker run --rm --entrypoint whoami architect-sandbox:latest

# Confirm uv is available
docker run --rm --entrypoint uv architect-sandbox:latest --version

# Confirm workspace directory
docker run --rm --entrypoint ls architect-sandbox:latest -la /workspace

# Check resource labels
docker inspect architect-sandbox:latest --format '{{index .Config.Labels "architect.resource.cpu"}}'
docker inspect architect-sandbox:latest --format '{{index .Config.Labels "architect.resource.memory_mb"}}'
```

Expected results: Python 3.12.x, user `sandbox`, uv version output, empty `/workspace` owned by sandbox, and label values `2` and `4096`.

---

## When to Rebuild

Rebuild the image when any of the following change:

- **Python version bump** -- update the `FROM python:3.12-slim` base tag.
- **New system packages** -- agents need a tool not currently installed (e.g., `jq`, `sqlite3`).
- **uv version pin** -- if you pin uv to a specific version instead of `latest`.
- **Security patches** -- periodically rebuild to pick up base image security updates.
- **Resource label changes** -- adjusting default CPU, memory, or disk limits.

After rebuilding, re-run the verification commands above and ensure the Execution Sandbox service's integration tests pass:

```bash
make test-integration
```
