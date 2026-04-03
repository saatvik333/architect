"""Security validation for sandbox commands and files."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from architect_common.logging import get_logger

logger = get_logger(component="security")

# ── Default workspace root used for path validation ──────────────
WORKSPACE_ROOT = Path("/workspace")

# -- Allowed binaries (allowlist - primary defense) --
ALLOWED_BINARIES: frozenset[str] = frozenset(
    {
        "python3",
        "python",
        "pip",
        "pip3",
        "uv",
        "pytest",
        "git",
        "cat",
        "ls",
        "mkdir",
        "cp",
        "mv",
        "touch",
        "echo",
        "cd",
        "pwd",
        "find",
        "grep",
        "sed",
        "awk",
        "head",
        "tail",
        "wc",
        "sort",
        "uniq",
        "diff",
        "tee",
        "chmod",
        "tar",
        "curl",
        "wget",
    }
)

# ── Blocked command patterns (secondary defense) ─────────────────────
# Each entry is a tuple of (compiled regex, human-readable reason).
# All patterns use ``re.IGNORECASE`` so that trivial case-mangling
# cannot bypass the filter.
_I = re.IGNORECASE

BLOCKED_COMMANDS: list[tuple[re.Pattern[str], str]] = [
    # ── Destructive filesystem operations ────────────────────────
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$", _I),
        "recursive force delete on root",
    ),
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*)?f[a-zA-Z]*r[a-zA-Z]*\s+/\s*$", _I),
        "recursive force delete on root",
    ),
    (re.compile(r"mkfs\b", _I), "filesystem formatting"),
    (re.compile(r"dd\s+.*of=/dev/", _I), "direct disk write"),
    (re.compile(r":(){ :\|:& };:", _I), "fork bomb"),
    # ── Permission / ownership abuse ────────────────────────────
    (
        re.compile(r"\bchmod\s+(-[a-zA-Z]*)?\s*777\s+/", _I),
        "world-writable root permissions",
    ),
    (
        re.compile(r"chmod\s+(777|a\+[rwx]|o\+[rwx])", _I),
        "dangerous permission grant",
    ),
    (re.compile(r"\bchown\s+.*\s+/", _I), "ownership change on root paths"),
    (
        re.compile(r"chown\s+\S+\s+(/etc|/usr|/bin|/sbin|/lib)", _I),
        "chown on system directory",
    ),
    # ── Mount / unmount ──────────────────────────────────────────
    (re.compile(r"\bmount\b", _I), "filesystem mount"),
    (re.compile(r"\bumount\b", _I), "filesystem unmount"),
    # ── Firewall & kernel ───────────────────────────────────────
    (re.compile(r"\biptables\b", _I), "firewall manipulation"),
    (re.compile(r"\bnftables\b", _I), "firewall manipulation"),
    (re.compile(r"\bsysctl\b", _I), "kernel parameter modification"),
    # ── Namespace / privilege-escalation ─────────────────────────
    (re.compile(r"\bnsenter\b", _I), "namespace escape"),
    (re.compile(r"\bunshare\b", _I), "namespace creation"),
    (re.compile(r"\bkexec\b", _I), "kernel replacement"),
    (re.compile(r"\binsmod\b", _I), "kernel module loading"),
    (re.compile(r"\bmodprobe\b", _I), "kernel module loading"),
    # ── Direct device / procfs / sysfs writes ───────────────────
    (re.compile(r">\s*/dev/sd[a-z]", _I), "direct block device write"),
    (re.compile(r">\s*/proc/", _I), "procfs write"),
    (re.compile(r">\s*/sys/", _I), "sysfs write"),
    # ── Remote code execution via piped download ────────────────
    (re.compile(r"\bcurl\b.*\|\s*(?:ba)?sh", _I), "pipe remote script to shell"),
    (re.compile(r"\bwget\b.*\|\s*(?:ba)?sh", _I), "pipe remote script to shell"),
    # Full-path variants for curl/wget
    (re.compile(r"/usr/bin/curl\b.*\|\s*(?:ba)?sh", _I), "pipe remote script to shell"),
    (re.compile(r"/usr/bin/wget\b.*\|\s*(?:ba)?sh", _I), "pipe remote script to shell"),
    # ── Device file creation ────────────────────────────────────
    (re.compile(r"mknod\b", _I), "device file creation"),
    # ── Dangerous find with exec ────────────────────────────────
    (re.compile(r"find\s+.*-exec\b", _I), "find with exec chain"),
    (re.compile(r"find\s+.*-execdir\b", _I), "find with execdir chain"),
    # ── Shell eval / exec builtins ──────────────────────────────
    (re.compile(r"\beval\s+", _I), "shell eval"),
    (re.compile(r"\bexec\s+", _I), "exec builtin"),
    # ── Shared library injection ────────────────────────────────
    (re.compile(r"LD_PRELOAD\s*=", _I), "shared library injection"),
    # ── Shared memory access ────────────────────────────────────
    (re.compile(r"/dev/shm\b", _I), "shared memory access"),  # nosec B108 # detection pattern, not usage
    # ── Decode-and-execute patterns ─────────────────────────────
    (re.compile(r"base64\s+-d", _I), "base64 decode (potential code execution)"),
    (re.compile(r"base64\s+--decode", _I), "base64 decode (potential code execution)"),
    # ── Process self-manipulation ───────────────────────────────
    (re.compile(r"/proc/self", _I), "process self-manipulation"),
    # ── Full-path variants for common dangerous binaries ────────
    (re.compile(r"/bin/rm\b", _I), "rm via full path"),
    (re.compile(r"/usr/bin/rm\b", _I), "rm via full path"),
    (re.compile(r"/usr/bin/curl\b.*\|\s*(?:ba)?sh", _I), "curl pipe to shell via full path"),
    (re.compile(r"/usr/bin/wget\b.*\|\s*(?:ba)?sh", _I), "wget pipe to shell via full path"),
    (re.compile(r"/sbin/mkfs", _I), "mkfs via full path"),
    (re.compile(r"/sbin/iptables\b", _I), "iptables via full path"),
    (re.compile(r"/usr/sbin/iptables\b", _I), "iptables via full path"),
    (re.compile(r"/sbin/modprobe\b", _I), "modprobe via full path"),
    (re.compile(r"/sbin/insmod\b", _I), "insmod via full path"),
    (re.compile(r"/sbin/sysctl\b", _I), "sysctl via full path"),
    (re.compile(r"/usr/sbin/sysctl\b", _I), "sysctl via full path"),
    (re.compile(r"/usr/sbin/nsenter\b", _I), "nsenter via full path"),
]

# ── Allowed network hosts ────────────────────────────────────────────
ALLOWED_NETWORK_HOSTS: list[str] = [
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "crates.io",
    "static.crates.io",
    "repo.maven.apache.org",
    "rubygems.org",
    "dl-cdn.alpinelinux.org",
    "deb.debian.org",
    "security.debian.org",
]

# ── Suspicious file-content patterns ─────────────────────────────────
_SUSPICIOUS_FILE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"), "potential AWS access key"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}"), "potential GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "potential API secret key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"), "private key material"),
    (re.compile(r"password\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "hardcoded password"),
]


def validate_command(command: str) -> tuple[bool, str | None]:
    """Check whether *command* is safe to execute in a sandbox.

    Uses an allowlist of permitted binaries as the primary defense,
    with the regex-based blocklist as a secondary layer.

    Returns:
        ``(True, None)`` when the command is allowed, or
        ``(False, reason)`` when the command should be rejected.
    """
    stripped = command.strip()

    if not stripped:
        return False, "empty command"

    # ── Primary defense: binary allowlist ─────────────────────────
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return False, "malformed command (unable to parse)"

    if not tokens:
        return False, "empty command after parsing"

    # Extract the base binary name, stripping any path prefix
    base_binary = Path(tokens[0]).name

    if base_binary not in ALLOWED_BINARIES:
        return False, f"binary not in allowlist: {base_binary}"

    # ── Secondary defense: regex blocklist ────────────────────────
    for pattern, reason in BLOCKED_COMMANDS:
        if pattern.search(stripped):
            return False, f"blocked: {reason}"

    return True, None


def _resolve_sandbox_path(
    raw_path: str,
    workspace_root: Path = WORKSPACE_ROOT,
) -> tuple[bool, str | None, Path | None]:
    """Canonicalize *raw_path* relative to *workspace_root*.

    Returns:
        ``(True, None, resolved_path)`` when the path is safe, or
        ``(False, reason, None)`` when it should be rejected.
    """
    path = Path(raw_path)

    # If the path is absolute it must live under workspace_root
    if path.is_absolute():
        try:
            resolved = path.resolve(strict=False)
        except (OSError, ValueError) as exc:
            return False, f"cannot resolve path {raw_path}: {exc}", None

        if not resolved.is_relative_to(workspace_root):
            return False, f"file path escapes workspace: {raw_path}", None

        return True, None, resolved

    # Relative path -- resolve against workspace_root
    combined = workspace_root / path
    try:
        resolved = combined.resolve(strict=False)
    except (OSError, ValueError) as exc:
        return False, f"cannot resolve path {raw_path}: {exc}", None

    if not resolved.is_relative_to(workspace_root):
        return False, f"path traversal detected: {raw_path}", None

    return True, None, resolved


def _check_symlink_escape(
    raw_path: str,
    workspace_root: Path = WORKSPACE_ROOT,
) -> tuple[bool, str | None]:
    """Reject *raw_path* if it is a symlink pointing outside *workspace_root*.

    Returns:
        ``(True, None)`` when the path is safe (or doesn't exist yet), or
        ``(False, reason)`` when a symlink escape is detected.
    """
    path = Path(raw_path) if Path(raw_path).is_absolute() else workspace_root / raw_path

    try:
        if path.is_symlink():
            target = path.resolve(strict=False)
            if not target.is_relative_to(workspace_root):
                return False, f"symlink escape detected: {raw_path} -> {target}"
    except (OSError, ValueError):
        # If we can't stat the path it doesn't exist yet -- not a symlink risk
        pass

    return True, None


def validate_files(
    files: dict[str, str],
    workspace_root: Path = WORKSPACE_ROOT,
) -> tuple[bool, str | None]:
    """Check whether file contents are safe to write into a sandbox.

    Performs path canonicalization and symlink-escape detection in
    addition to the original content scanning.

    Returns:
        ``(True, None)`` when all files pass, or
        ``(False, reason)`` describing the first violation found.
    """
    for path, content in files.items():
        # ── Path canonicalization ────────────────────────────────
        safe, reason, _resolved = _resolve_sandbox_path(path, workspace_root)
        if not safe:
            return False, reason

        # ── Symlink escape detection ────────────────────────────
        safe, reason = _check_symlink_escape(path, workspace_root)
        if not safe:
            return False, reason

        # ── Scan content for secrets ────────────────────────────
        for pattern, pattern_reason in _SUSPICIOUS_FILE_PATTERNS:
            if pattern.search(content):
                return False, f"{pattern_reason} in {path}"

    return True, None
