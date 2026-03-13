"""Security validation for sandbox commands and files."""

from __future__ import annotations

import re

# ── Blocked command patterns ─────────────────────────────────────────
# Each entry is a tuple of (compiled regex, human-readable reason).
BLOCKED_COMMANDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$"),
        "recursive force delete on root",
    ),
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*)?f[a-zA-Z]*r[a-zA-Z]*\s+/\s*$"),
        "recursive force delete on root",
    ),
    (re.compile(r"mkfs\b"), "filesystem formatting"),
    (re.compile(r"dd\s+.*of=/dev/"), "direct disk write"),
    (re.compile(r":(){ :\|:& };:"), "fork bomb"),
    (re.compile(r"\bchmod\s+(-[a-zA-Z]*)?\s*777\s+/"), "world-writable root permissions"),
    (re.compile(r"\bchown\s+.*\s+/"), "ownership change on root paths"),
    (re.compile(r"\bmount\b"), "filesystem mount"),
    (re.compile(r"\bumount\b"), "filesystem unmount"),
    (re.compile(r"\biptables\b"), "firewall manipulation"),
    (re.compile(r"\bnftables\b"), "firewall manipulation"),
    (re.compile(r"\bsysctl\b"), "kernel parameter modification"),
    (re.compile(r"\bnsenter\b"), "namespace escape"),
    (re.compile(r"\bunshare\b"), "namespace creation"),
    (re.compile(r"\bkexec\b"), "kernel replacement"),
    (re.compile(r"\binsmod\b"), "kernel module loading"),
    (re.compile(r"\bmodprobe\b"), "kernel module loading"),
    (re.compile(r">\s*/dev/sd[a-z]"), "direct block device write"),
    (re.compile(r">\s*/proc/"), "procfs write"),
    (re.compile(r">\s*/sys/"), "sysfs write"),
    (re.compile(r"\bcurl\b.*\|\s*(?:ba)?sh"), "pipe remote script to shell"),
    (re.compile(r"\bwget\b.*\|\s*(?:ba)?sh"), "pipe remote script to shell"),
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

    Returns:
        ``(True, None)`` when the command is allowed, or
        ``(False, reason)`` when the command should be rejected.
    """
    stripped = command.strip()

    if not stripped:
        return False, "empty command"

    for pattern, reason in BLOCKED_COMMANDS:
        if pattern.search(stripped):
            return False, f"blocked: {reason}"

    return True, None


def validate_files(files: dict[str, str]) -> tuple[bool, str | None]:
    """Check whether file contents are safe to write into a sandbox.

    Returns:
        ``(True, None)`` when all files pass, or
        ``(False, reason)`` describing the first violation found.
    """
    for path, content in files.items():
        # Reject absolute paths that escape the workspace
        if path.startswith("/") and not path.startswith("/workspace"):
            return False, f"file path escapes workspace: {path}"

        # Reject path traversal
        if ".." in path:
            return False, f"path traversal detected: {path}"

        # Scan content for secrets
        for pattern, reason in _SUSPICIOUS_FILE_PATTERNS:
            if pattern.search(content):
                return False, f"{reason} in {path}"

    return True, None
