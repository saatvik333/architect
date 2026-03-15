"""Git commit integration for the Coding Agent."""

from __future__ import annotations

import asyncio
from pathlib import Path

from architect_common.logging import get_logger
from coding_agent.models import GeneratedFile

logger = get_logger(component="coding_agent.git")


class GitCommitError(Exception):
    """Raised when a git commit operation fails."""


class GitCommitter:
    """Handles writing generated files and committing them to a git repository."""

    async def commit(
        self,
        files: list[GeneratedFile],
        message: str,
        repo_path: str,
    ) -> str:
        """Write generated files to disk and commit them.

        Args:
            files: The generated files to write and commit.
            message: The git commit message.
            repo_path: Path to the git repository root.

        Returns:
            The 40-character hex commit hash.

        Raises:
            GitCommitError: If the repo path is invalid, not a git repo,
                a file path escapes the repo, or a git command fails.
        """
        repo = Path(repo_path).resolve()

        if not repo.is_dir():
            raise GitCommitError(f"Repository path does not exist: {repo}")

        git_dir = repo / ".git"
        if not git_dir.exists():
            raise GitCommitError(f"Not a git repository (no .git directory): {repo}")

        if not files:
            raise GitCommitError("No files to commit")

        # Validate all paths before writing anything
        resolved_paths: list[Path] = []
        for f in files:
            file_path = (repo / f.path).resolve()
            # Prevent path traversal: resolved path must be inside repo
            try:
                file_path.relative_to(repo)
            except ValueError:
                raise GitCommitError(
                    f"Path traversal detected: {f.path!r} resolves outside repository"
                ) from None
            resolved_paths.append(file_path)

        # Write files to disk
        relative_paths: list[str] = []
        for f, file_path in zip(files, resolved_paths, strict=True):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content, encoding="utf-8")
            relative_paths.append(f.path)
            logger.debug("wrote file", path=f.path)

        # Stage specific files only (never git add .)
        await self._run_git(repo, "add", "--", *relative_paths)

        # Commit
        await self._run_git(repo, "commit", "-m", message)

        # Get the commit hash
        commit_hash = await self._run_git(repo, "rev-parse", "HEAD")
        commit_hash = commit_hash.strip()

        if len(commit_hash) != 40:
            raise GitCommitError(f"Unexpected commit hash format: {commit_hash!r}")

        logger.info(
            "committed code",
            commit_hash=commit_hash,
            file_count=len(files),
        )

        return commit_hash

    @staticmethod
    async def _run_git(repo: Path, *args: str) -> str:
        """Execute a git command in the given repository.

        Args:
            repo: The repository working directory.
            *args: Arguments to pass to ``git``.

        Returns:
            The stdout output from the command.

        Raises:
            GitCommitError: If the command exits with a non-zero status.
        """
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise GitCommitError(
                f"git {args[0]} failed (exit {proc.returncode}): "
                f"{stderr.decode().strip() or stdout.decode().strip()}"
            )

        return stdout.decode()
