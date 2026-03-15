"""Tests for GitCommitter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coding_agent.git import GitCommitError, GitCommitter
from coding_agent.models import GeneratedFile


def _init_repo(path: Path) -> None:
    """Initialise a bare git repo with an initial commit."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    # Create an initial commit so HEAD exists
    readme = path / "README.md"
    readme.write_text("init")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


class TestGitCommitter:
    """Tests for :class:`GitCommitter`."""

    async def test_commit_creates_files_and_returns_hash(self, tmp_path: Path) -> None:
        """A successful commit writes files and returns a 40-char hash."""
        _init_repo(tmp_path)

        files = [
            GeneratedFile(path="src/hello.py", content="print('hello')\n"),
            GeneratedFile(path="tests/test_hello.py", content="def test(): pass\n", is_test=True),
        ]

        committer = GitCommitter()
        commit_hash = await committer.commit(
            files=files,
            message="feat: add hello",
            repo_path=str(tmp_path),
        )

        # Verify the commit hash format
        assert len(commit_hash) == 40
        assert all(c in "0123456789abcdef" for c in commit_hash)

        # Verify files were written (ArchitectBase strips trailing whitespace)
        assert "print('hello')" in (tmp_path / "src" / "hello.py").read_text()
        assert "def test(): pass" in (tmp_path / "tests" / "test_hello.py").read_text()

    async def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """File paths that escape the repository root should be rejected."""
        _init_repo(tmp_path)

        files = [
            GeneratedFile(path="../../etc/passwd", content="malicious"),
        ]

        committer = GitCommitter()
        with pytest.raises(GitCommitError, match="Path traversal detected"):
            await committer.commit(
                files=files,
                message="bad commit",
                repo_path=str(tmp_path),
            )

    async def test_error_when_not_a_git_repo(self, tmp_path: Path) -> None:
        """Committing in a directory that is not a git repo should raise."""
        files = [GeneratedFile(path="file.py", content="x = 1\n")]

        committer = GitCommitter()
        with pytest.raises(GitCommitError, match="Not a git repository"):
            await committer.commit(
                files=files,
                message="test",
                repo_path=str(tmp_path),
            )

    async def test_error_when_repo_path_missing(self) -> None:
        """Committing with a non-existent path should raise."""
        files = [GeneratedFile(path="file.py", content="x = 1\n")]

        committer = GitCommitter()
        with pytest.raises(GitCommitError, match="does not exist"):
            await committer.commit(
                files=files,
                message="test",
                repo_path="/nonexistent/path/abc123",
            )

    async def test_empty_file_list_rejected(self, tmp_path: Path) -> None:
        """An empty file list should raise immediately."""
        _init_repo(tmp_path)

        committer = GitCommitter()
        with pytest.raises(GitCommitError, match="No files to commit"):
            await committer.commit(
                files=[],
                message="empty",
                repo_path=str(tmp_path),
            )

    async def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """Parent directories should be created automatically."""
        _init_repo(tmp_path)

        files = [
            GeneratedFile(path="a/b/c/deep.py", content="deep = True\n"),
        ]

        committer = GitCommitter()
        commit_hash = await committer.commit(
            files=files,
            message="feat: deep file",
            repo_path=str(tmp_path),
        )

        assert len(commit_hash) == 40
        assert (tmp_path / "a" / "b" / "c" / "deep.py").exists()
