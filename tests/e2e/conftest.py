"""Shared fixtures for end-to-end tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with an initial commit.

    Yields the path to the repo root, then cleans up after.
    """
    repo = tmp_path / "test-repo"
    repo.mkdir()

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
    # Configure user for this repo
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Add a dummy file and initial commit
    dummy = repo / "README.md"
    dummy.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )

    yield repo


@pytest.fixture
def poll_task_status():
    """Return an async helper that polls a URL for task completion.

    Usage::

        status = await poll_task_status(client, url, timeout=120)
    """

    async def _poll(
        client: Any,
        url: str,
        *,
        timeout: float = 120.0,
        interval: float = 2.0,
        terminal_statuses: frozenset[str] = frozenset({"completed", "failed", "cancelled"}),
    ) -> dict[str, Any]:
        """Poll GET ``url`` until the returned status is terminal or timeout.

        Args:
            client: An ``httpx.AsyncClient`` instance.
            url: The full URL to poll.
            timeout: Maximum seconds to wait.
            interval: Seconds between polls.
            terminal_statuses: Status values that indicate the task is done.

        Returns:
            The final JSON response body.

        Raises:
            TimeoutError: If the task does not reach a terminal status in time.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        last_data: dict[str, Any] = {}

        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get(url)
            resp.raise_for_status()
            last_data = resp.json()
            status = last_data.get("status", "")
            if status in terminal_statuses:
                return last_data
            await asyncio.sleep(interval)

        raise TimeoutError(
            f"Task at {url} did not reach terminal status within {timeout}s. "
            f"Last status: {last_data.get('status', 'unknown')}"
        )

    return _poll
