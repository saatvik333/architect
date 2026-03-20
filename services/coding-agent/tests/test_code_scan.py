"""Tests for post-generation code security scanning."""

from __future__ import annotations

from coding_agent.coder import _scan_generated_code
from coding_agent.models import GeneratedFile


class TestCodeScan:
    def test_detects_os_system(self) -> None:
        files = [GeneratedFile(path="main.py", content="os.system('rm -rf /')", is_test=False)]
        warnings = _scan_generated_code(files)
        assert len(warnings) >= 1
        assert any("os.system" in w["pattern"] for w in warnings)

    def test_detects_eval(self) -> None:
        files = [GeneratedFile(path="main.py", content="result = eval(user_input)", is_test=False)]
        warnings = _scan_generated_code(files)
        assert any("eval" in w["pattern"] for w in warnings)

    def test_clean_code_no_warnings(self) -> None:
        files = [
            GeneratedFile(
                path="main.py",
                content="def hello():\n    return 'world'",
                is_test=False,
            )
        ]
        warnings = _scan_generated_code(files)
        assert len(warnings) == 0

    def test_detects_subprocess_shell(self) -> None:
        files = [
            GeneratedFile(
                path="main.py",
                content="subprocess.run(cmd, shell=True)",
                is_test=False,
            )
        ]
        warnings = _scan_generated_code(files)
        assert len(warnings) >= 1
