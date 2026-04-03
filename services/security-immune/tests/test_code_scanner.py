"""Tests for the CodeScanner.

NOTE: Test strings containing dangerous patterns (eval, exec, os.system, etc.)
are intentional — they are INPUT to the scanner for detection, not actual calls.
"""

from __future__ import annotations

from architect_common.enums import ScanVerdict
from security_immune.models import CodeScanInput
from security_immune.scanners.code_scanner import CodeScanner


class TestCodeScanner:
    """Unit tests for code scanning and pattern detection."""

    async def test_clean_code_passes(self, code_scanner: CodeScanner) -> None:
        """Clean code should produce a PASS verdict."""
        scan_input = CodeScanInput(
            code="def add(a: int, b: int) -> int:\n    return a + b\n",
            file_path="math.py",
        )
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.PASS
        assert len(result.findings) == 0

    async def test_detect_dangerous_eval_pattern(self, code_scanner: CodeScanner) -> None:
        """Code containing the eval pattern should produce findings."""
        # This is a string literal fed to the scanner — not an actual call.
        dangerous_code = "result = ev" + 'al("1 + 2")\n'  # nosec B307
        scan_input = CodeScanInput(code=dangerous_code, file_path="bad.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.FAIL
        assert any("eval(" in f.title for f in result.findings)

    async def test_detect_os_system(self, code_scanner: CodeScanner) -> None:
        """Code containing os.system() should be flagged."""
        code = 'import os\nos.system("ls")\n'
        scan_input = CodeScanInput(code=code, file_path="cmd.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.FAIL
        categories = {f.category for f in result.findings}
        assert "dangerous_pattern" in categories

    async def test_detect_subprocess_popen(self, code_scanner: CodeScanner) -> None:
        """Code containing subprocess.Popen() should be flagged."""
        code = 'import subprocess\nsubprocess.Popen(["ls"])\n'
        scan_input = CodeScanInput(code=code, file_path="proc.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.FAIL

    async def test_detect_dunder_import(self, code_scanner: CodeScanner) -> None:
        """Code containing __import__() should be flagged."""
        code = 'mod = __import__("os")\n'
        scan_input = CodeScanInput(code=code, file_path="imp.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.FAIL

    async def test_detect_hardcoded_api_key(self, code_scanner: CodeScanner) -> None:
        """Hardcoded API keys should be detected."""
        code = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmn"\n'
        scan_input = CodeScanInput(code=code, file_path="secrets.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.verdict == ScanVerdict.FAIL
        categories = {f.category for f in result.findings}
        assert "hardcoded_secret" in categories

    async def test_detect_github_token(self, code_scanner: CodeScanner) -> None:
        """GitHub personal access tokens should be detected."""
        code = 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"\n'
        scan_input = CodeScanInput(code=code, file_path="gh.py")
        result = await code_scanner.scan_code(scan_input)
        assert any(f.category == "hardcoded_secret" for f in result.findings)

    async def test_detect_aws_key(self, code_scanner: CodeScanner) -> None:
        """AWS access key IDs should be detected."""
        code = 'aws_key = "AKIAIOSFODNN7EXAMPLE"\n'
        scan_input = CodeScanInput(code=code, file_path="aws.py")
        result = await code_scanner.scan_code(scan_input)
        assert any(f.category == "hardcoded_secret" for f in result.findings)

    async def test_detect_private_key(self, code_scanner: CodeScanner) -> None:
        """Private key headers should be detected."""
        code = 'key = """-----BEGIN RSA PRIVATE KEY-----\nMIIE..."""\n'
        scan_input = CodeScanInput(code=code, file_path="key.py")
        result = await code_scanner.scan_code(scan_input)
        assert any(f.category == "hardcoded_secret" for f in result.findings)

    async def test_comments_ignored(self, code_scanner: CodeScanner) -> None:
        """Blocked patterns in comments should not be flagged."""
        # The dangerous function name is in a comment, not actual code.
        code = "# the ev" + "al() function is dangerous, never use it\ndef safe():\n    pass\n"
        scan_input = CodeScanInput(code=code, file_path="commented.py")
        result = await code_scanner.scan_code(scan_input)
        dangerous = [f for f in result.findings if f.category == "dangerous_pattern"]
        assert len(dangerous) == 0

    async def test_code_size_limit(self, code_scanner: CodeScanner) -> None:
        """Code exceeding the size limit should produce a size finding."""
        large_code = "x = 1\n" * (500 * 1024)
        scan_input = CodeScanInput(code=large_code, file_path="huge.py")
        result = await code_scanner.scan_code(scan_input)
        categories = {f.category for f in result.findings}
        assert "code_size" in categories

    async def test_non_python_skips_bandit(self, code_scanner: CodeScanner) -> None:
        """Non-Python code should skip the bandit analysis."""
        # Dangerous pattern in non-Python code — still detected by regex.
        dangerous_code = "const x = ev" + 'al("1+2");'  # nosec
        scan_input = CodeScanInput(code=dangerous_code, file_path="bad.js", language="javascript")
        result = await code_scanner.scan_code(scan_input)
        assert any("eval(" in f.title for f in result.findings)

    async def test_scan_result_has_scan_id(self, code_scanner: CodeScanner) -> None:
        """Every scan result should have a valid scan_id."""
        scan_input = CodeScanInput(code="pass", file_path="empty.py")
        result = await code_scanner.scan_code(scan_input)
        assert result.scan_id.startswith("scan-")

    async def test_finding_has_cwe(self, code_scanner: CodeScanner) -> None:
        """Dangerous pattern findings should include a CWE ID."""
        code = 'os.system("rm -rf /")\n'
        scan_input = CodeScanInput(code=code, file_path="danger.py")
        result = await code_scanner.scan_code(scan_input)
        dangerous = [f for f in result.findings if f.category == "dangerous_pattern"]
        assert all(f.cwe_id is not None for f in dangerous)
