# Docker Security Runbook

This runbook covers the security model of ARCHITECT's Execution Sandbox, which uses Docker containers to run untrusted LLM-generated code.

---

## Why the sandbox mounts the Docker socket

The Execution Sandbox service (`services/execution-sandbox/`) creates, manages, and destroys Docker containers programmatically via the Docker SDK for Python. To do this, it needs access to the Docker daemon.

In the current `docker-compose.yml` configuration, the sandbox service mounts the host's Docker socket (`/var/run/docker.sock`) as a volume. This allows the sandbox service to issue Docker API calls (create container, exec, copy files, remove container) without requiring Docker-in-Docker or a remote Docker daemon.

This is the simplest and most common approach for services that need to manage sibling containers. It is used in development, CI, and single-machine deployments.

---

## Security implications

Mounting the Docker socket grants the sandbox service **host-level Docker access**. If the sandbox service process is compromised (e.g., through a vulnerability in FastAPI, a dependency, or the Docker SDK), an attacker could:

1. **Create privileged containers:** Launch a container with `--privileged` or with host filesystem mounts, escaping the isolation boundary entirely.
2. **Access other containers:** Inspect, stop, or exec into any container on the same Docker daemon, including the database, Redis, Temporal, and other ARCHITECT services.
3. **Read host filesystem:** Mount arbitrary host paths into a new container.
4. **Exfiltrate data:** Create containers with network access to send data to external servers.

The Docker socket is effectively equivalent to root access on the host. This is a known and accepted trade-off for development and single-machine deployments, but it must be mitigated for any production or multi-tenant environment.

---

## Docker Socket Proxy (Primary Mitigation)

The execution sandbox communicates with Docker through a Tecnativa docker-socket-proxy
that restricts API access:

**Allowed operations:**
- Container lifecycle: create, start, stop, remove, inspect
- Exec into containers

**Blocked operations:**
- Image management (pull, build, tag, push)
- Volume management
- Network management
- Privileged container creation
- Swarm operations

### Configuration

In `infra/docker-compose.yml`, the proxy runs as a separate service. The sandbox
connects via `ARCHITECT_SANDBOX_DOCKER_HOST=tcp://docker-socket-proxy:2375`.

### Local Development

For local development without docker-compose, the sandbox falls back to the direct
Unix socket at `/var/run/docker.sock`. This is acceptable for development but should
NOT be used in production.

---

## Current mitigations

The sandbox containers themselves (the containers created by the Execution Sandbox service to run generated code) have multiple security layers applied:

### Seccomp profile

A custom seccomp profile (`infra/seccomp/sandbox-profile.json`) is applied to every sandbox container. It blocks dangerous syscalls including `ptrace`, `mount`, `unshare`, `CLONE_NEWUSER`, `keyctl`, `syslog`, `pivot_root`, `bpf`, `perf_event_open`, and kernel module operations. This reduces the kernel attack surface available to code running inside the sandbox.

### Read-only root filesystem

Sandbox containers are created with `read_only=True`. The root filesystem is mounted read-only. Only `/workspace` (tmpfs) and `/tmp` are writable. This prevents generated code from modifying the container's system files or installing packages.

### Dropped capabilities

All Linux capabilities are dropped (`cap_drop=["ALL"]`), and only the five minimal capabilities needed for normal operation are added back. This prevents privilege escalation, network configuration changes, and other capability-gated operations.

### Non-root user

All commands inside sandbox containers execute as UID 1000 (non-root). Even if a capability or seccomp bypass were found, the process would not have root privileges inside the container.

### Resource limits

Each sandbox container is constrained by:

- **CPU:** Limited cores (default: 1 CPU)
- **Memory:** Hard cap (default: 512 MB) with OOM kill on breach
- **PIDs:** Limit of 256 processes (fork bomb protection)
- **Disk:** tmpfs size limit on `/workspace`
- **Timeout:** Wall-clock execution limit per command (default: 60 seconds)
- **Block I/O:** Reduced `blkio_weight` (100)

### Network isolation

Sandbox containers are created with `network_mode: none`. No inbound or outbound network traffic is possible from inside the sandbox.

### Command allowlist

The `SecurityValidator` validates every command before execution against an allowlist with `shlex.split()` parsing. Only explicitly permitted commands are allowed. This prevents command injection, privilege escalation attempts, and access to dangerous binaries.

### Path validation

File paths are validated using `Path.is_relative_to()` to prevent path traversal attacks. Symlink escapes outside the workspace root are detected and rejected. Tar archive member names are validated to prevent tar slip (zip slip) vulnerabilities.

---

## Future alternatives

The Docker socket mount is the primary security concern. These alternatives eliminate or reduce the risk:

### Rootless Docker

Run the Docker daemon in rootless mode, where the daemon itself runs as a non-root user. This limits the blast radius of a Docker socket compromise -- an attacker gains access to the user's namespace, not the host root. Requires systemd user session support and has some limitations (e.g., no `--privileged` containers, limited network modes). This is the lowest-friction improvement.

### Docker-in-Docker (DinD)

Run a dedicated Docker daemon inside a container. The sandbox service communicates with this inner daemon instead of the host daemon. The inner daemon cannot access host containers or the host filesystem (beyond its own volume mounts). The DinD container itself must be privileged, but the blast radius is contained to the DinD container's storage volume. Adds operational complexity (managing a nested daemon) and slight performance overhead.

### Docker socket proxy

Interpose an authorizing proxy (e.g., Tecnativa docker-socket-proxy, or HAProxy with ACLs) between the sandbox service and the Docker socket. The proxy restricts which Docker API endpoints are accessible. For example, it can allow `POST /containers/create` and `DELETE /containers/{id}` but deny `POST /containers/create` with `Privileged: true` or host volume mounts. This preserves the socket-based architecture while adding fine-grained access control.

### Sysbox runtime

Use the Sysbox OCI runtime, which provides VM-like isolation for Docker containers without requiring a VM. Sysbox containers can run Docker inside them without `--privileged` and without mounting the host socket. This is the most transparent migration path from the current setup.

---

## Operational guidance

### Never expose the sandbox port publicly

The Execution Sandbox service listens on port 8003 by default. This port must never be exposed to the public internet or untrusted networks. In `docker-compose.yml`, the sandbox port should only be published to `127.0.0.1` or accessed via the internal Docker network.

If using a reverse proxy or load balancer, ensure the sandbox service is excluded from external routing. Only the API Gateway (port 8000) should be externally accessible.

### Monitor container creation logs

The Docker daemon logs every container creation event. Monitor these logs for unexpected container attributes:

- Containers created with `--privileged`
- Containers with host filesystem mounts (bind mounts to `/`, `/etc`, `/var/run/docker.sock`, etc.)
- Containers with `network_mode: host`
- Containers running as root (UID 0)

In a production deployment, use Docker event monitoring (`docker events --filter type=container`) or a container security tool (Falco, Sysdig) to alert on policy-violating container configurations.

### Audit sandbox sessions

Every sandbox session is logged with:

- Container ID
- Commands executed (with timestamps and exit codes)
- Files written and read
- Resource usage

Review these logs periodically, especially after security incidents or when investigating unexpected behavior. The `SandboxSession` audit trail is stored in the database and accessible via the sandbox service API.

### Keep the base image updated

The sandbox base image (`python:3.12-slim` with the custom `Dockerfile.sandbox`) should be rebuilt regularly to pick up security patches in the base OS and Python runtime. Pin the base image digest in CI to ensure reproducibility, and update it on a regular cadence (at least monthly).
