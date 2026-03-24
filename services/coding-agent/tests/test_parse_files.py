"""Tests for CodeGenerator._parse_files with edge cases."""

from coding_agent.coder import CodeGenerator


class TestParseFiles:
    def test_single_file(self) -> None:
        output = '```python\n# src/main.py\ndef hello():\n    return "world"\n```'
        files = CodeGenerator._parse_files(output)
        assert len(files) == 1
        assert files[0].path == "src/main.py"
        assert "hello" in files[0].content

    def test_multiple_files(self) -> None:
        output = "```python\n# src/a.py\nx = 1\n```\n\n```python\n# src/b.py\ny = 2\n```"
        files = CodeGenerator._parse_files(output)
        assert len(files) == 2

    def test_no_code_blocks(self) -> None:
        files = CodeGenerator._parse_files("No code here, just text.")
        assert len(files) == 0

    def test_duplicate_paths_keeps_last(self) -> None:
        output = (
            "```python\n# src/main.py\nold = True\n```\n\n```python\n# src/main.py\nnew = True\n```"
        )
        files = CodeGenerator._parse_files(output)
        assert len(files) == 1
        assert "new" in files[0].content

    def test_test_file_detection(self) -> None:
        output = "```python\n# tests/test_main.py\ndef test_it(): pass\n```"
        files = CodeGenerator._parse_files(output)
        assert len(files) == 1
        assert files[0].is_test is True

    def test_no_language_hint_still_matches(self) -> None:
        """Code fence without explicit language still matches since the regex
        makes the language hint optional (``(?:python|py)?``)."""
        output = "```\n# no_lang.py\ncode here\n```"
        files = CodeGenerator._parse_files(output)
        assert len(files) == 1
        assert files[0].path == "no_lang.py"

    def test_non_python_language_hint_no_match(self) -> None:
        """Code fences with a non-Python language should not match."""
        output = '```javascript\n# script.py\nconsole.log("hi")\n```'
        files = CodeGenerator._parse_files(output)
        assert len(files) == 0

    def test_empty_content(self) -> None:
        output = "```python\n# src/empty.py\n\n```"
        files = CodeGenerator._parse_files(output)
        assert len(files) == 1
        assert files[0].content.strip() == ""
