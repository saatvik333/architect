# ADR-004: Docker-Based Sandboxing for Code Execution

**Status:** Accepted

**Date:** 2025-01-15

---

## Context

ARCHITECT generates code autonomously using LLMs and then executes that code to verify correctness through its evaluation pipeline (compilation checks, unit tests, integration tests). By definition, LLM-generated code is **untrusted** -- it may contain bugs, infinite loops, excessive resource consumption, or inadvertent security risks. The system must:

1. **Isolate execution from the host:** Generated code must never access the host filesystem, network, or processes. A buggy or malicious program must not be able to escape its execution environment.
2. **Enforce resource limits:** CPU, memory, disk, and wall-clock time must be bounded so that runaway processes (infinite loops, memory leaks, fork bombs) cannot degrade the host system or other sandboxes.
3. **Provide a reproducible environment:** Each execution must start from a known, clean state. Side effects from one execution must not leak into the next.
4. **Support audit and observability:** Every command executed in a sandbox must be logged with timestamps, exit codes, and output for debugging and security review.
5. **Be operationally simple:** The sandboxing solution must be deployable on standard development machines and CI environments without specialized kernel configurations or hardware support.

The Execution Sandbox service manages the full lifecycle: creating containers, writing code files via tar archives, executing commands, collecting output, and destroying containers when done.

## Decision

We adopt **Docker containers** as the sandboxing mechanism for all code execution in ARCHITECT, with the following security layers:

### Container configuration

- **Base image:** A minimal Python image (e.g., `python:3.12-slim`) with no unnecessary packages.
- **Non-root user:** All commands execute as UID 1000 inside the container. The container never runs as root.
- **Read-only root filesystem:** The container's root filesystem is mounted read-only. Only the `/workspace` directory (a tmpfs mount) and `/tmp` are writable.
- **No network access:** Containers are created with `network_mode: none`, preventing any outbound or inbound network traffic.
- **Resource limits:** Each container is constrained by `ResourceLimits` specifying:
  - CPU: limited cores (e.g., 1 CPU)
  - Memory: hard cap (e.g., 512 MB)
  - Disk: tmpfs size limit on `/workspace`
  - Timeout: wall-clock execution limit per command (e.g., 60 seconds)

### Security validation

The `SecurityValidator` inspects every command before execution and rejects commands that:
- Attempt privilege escalation (`sudo`, `su`, `chmod +s`, etc.)
- Access host-sensitive paths (`/proc`, `/sys`, `/dev`, etc.)
- Attempt network operations (`curl`, `wget`, `nc`, `ssh`, etc.)
- Use container escape techniques (`nsenter`, `mount`, `chroot`, etc.)

### Lifecycle

Each sandbox session maps to exactly one Docker container:

1. `DockerExecutor.create()` -- pulls/creates a container with the configured limits and security settings.
2. `DockerExecutor.write_files()` -- writes code files into `/workspace` via tar archive injection.
3. `DockerExecutor.execute()` -- runs a command inside the container, captures stdout/stderr, enforces timeout.
4. `DockerExecutor.read_files()` -- extracts result files from `/workspace` via tar archive.
5. `DockerExecutor.destroy()` -- forcefully removes the container and all associated resources.

All operations are logged in a `SandboxSession` audit trail with timestamps, commands, exit codes, and resource usage.

### Alternatives considered

1. **gVisor (runsc):** Google's user-space kernel that intercepts system calls and provides stronger isolation than standard Docker. Offers better security guarantees by reducing the host kernel attack surface. However, gVisor introduces performance overhead (10-30% for I/O-heavy workloads), requires a custom OCI runtime configuration, and has compatibility issues with some Python libraries that use exotic syscalls. The additional security is valuable but not necessary for Phase 1 where the threat model is accidental resource exhaustion, not adversarial container escape.

2. **Firecracker microVMs:** Amazon's lightweight VM manager used by AWS Lambda. Provides true hardware-level isolation with sub-second boot times. However, Firecracker requires KVM support (not available in all CI environments or nested virtualization setups), has a more complex API than Docker, and requires building and managing VM images rather than container images. The operational complexity is significantly higher than Docker for a comparable level of isolation against our current threat model.

3. **Nsjail:** A lightweight process isolation tool using Linux namespaces and seccomp-bpf. More granular control over syscall filtering than Docker. However, Nsjail is less widely known, has a smaller community, limited documentation, and no ecosystem of base images. Developers would need to learn a new tool rather than leveraging existing Docker expertise.

4. **WebAssembly (Wasm) sandboxing:** Running generated code in a Wasm runtime (e.g., Wasmtime, Wasmer). Provides strong sandboxing with fine-grained capability control. However, Python support in Wasm is experimental (CPython compiled to Wasm has significant limitations), many Python packages with C extensions do not work in Wasm, and the developer experience for debugging Wasm-sandboxed Python code is poor. Not viable for a Python-centric system.

## Consequences

### Positive

- **Familiar tooling:** Docker is the most widely adopted containerization platform. Every developer on the team already knows how to build, run, and debug Docker containers. No new tooling to learn.
- **Configurable resource limits:** Docker's built-in `--memory`, `--cpus`, and timeout mechanisms provide straightforward resource bounding. The `ResourceLimits` model makes these configurable per sandbox session, allowing different limits for different task types (e.g., more memory for integration tests).
- **Comprehensive audit trail:** Every command, its exit code, stdout/stderr, and resource consumption is logged in the `SandboxSession`. This audit trail is essential for debugging evaluation failures and for the Security Immune system (Phase 3) to detect suspicious patterns.
- **Layered security:** The combination of non-root user, read-only rootfs, network isolation, command blocklist, and resource limits provides defense-in-depth. No single layer is solely responsible for security.
- **Easy local development:** Developers can run sandboxes on their local machines with just Docker installed. No specialized kernel modules, hypervisor support, or custom runtime configuration required.
- **Reproducible state:** Each container starts from the same base image with an empty `/workspace`. There is no state leakage between sandbox sessions.

### Negative

- **Shared kernel:** Docker containers share the host kernel. A kernel vulnerability could theoretically allow container escape. This risk is accepted for Phase 1 and can be mitigated in later phases by adding gVisor as an optional runtime for high-security workloads.
- **Docker daemon dependency:** The Execution Sandbox service requires a running Docker daemon on the host. In CI environments, this means Docker-in-Docker or a mounted Docker socket, both of which have their own security considerations.
- **Container startup latency:** Creating a new Docker container takes 1-3 seconds depending on the host. For tasks that require many rapid sandbox invocations, this latency adds up. This can be mitigated with container pooling (pre-warming containers) in later phases.
- **Image management:** The base sandbox image must be kept updated with security patches and appropriate Python versions. Image size affects pull times in CI. A container registry and image build pipeline will be needed as the system matures.
- **Resource overhead:** Each Docker container carries some fixed overhead (memory for the container runtime, filesystem layers). Running many concurrent sandboxes requires proportionally more host resources than lighter-weight alternatives like Nsjail or Wasm.
