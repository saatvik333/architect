"""Host-side workspace file management for sandbox containers."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
import uuid

from architect_common.logging import get_logger

logger = get_logger(component="file_manager")


class FileManager:
    """Creates, populates, and cleans up temporary workspace directories.

    Workspaces live on the host and can be bind-mounted or tarred into
    Docker containers.
    """

    def __init__(self, workspace_root: str = "/tmp/architect-sandboxes") -> None:  # nosec B108 # configurable default for sandbox workspaces
        self._workspace_root = workspace_root
        os.makedirs(self._workspace_root, exist_ok=True)

    async def prepare_workspace(self, files: dict[str, str]) -> str:
        """Create a temp directory under *workspace_root* and write *files* into it.

        Args:
            files: Mapping of ``relative_path -> file_content``.

        Returns:
            Absolute path to the newly created workspace directory.
        """

        def _write() -> str:
            workspace_id = f"ws-{uuid.uuid4().hex[:12]}"
            workspace_path = os.path.join(self._workspace_root, workspace_id)
            os.makedirs(workspace_path, exist_ok=True)

            for relative_path, content in files.items():
                # Sanitize path: strip leading slashes, reject traversal
                clean_path = relative_path.lstrip("/")
                if ".." in clean_path:
                    logger.warning("skipping_path_traversal", path=relative_path)
                    continue

                full_path = os.path.join(workspace_path, clean_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, "w") as fh:
                    fh.write(content)

            logger.info(
                "workspace_prepared",
                workspace_path=workspace_path,
                file_count=len(files),
            )
            return workspace_path

        return await asyncio.to_thread(_write)

    async def collect_outputs(self, workspace_path: str, patterns: list[str]) -> dict[str, str]:
        """Read files matching *patterns* from *workspace_path*.

        Args:
            workspace_path: Absolute host path to the workspace.
            patterns: Glob patterns (e.g. ``["*.py", "output/*.txt"]``).

        Returns:
            Mapping of ``relative_path -> file_content`` for matching files.
        """

        def _collect() -> dict[str, str]:
            results: dict[str, str] = {}

            if not os.path.isdir(workspace_path):
                logger.warning("workspace_not_found", workspace_path=workspace_path)
                return results

            for root, _dirs, filenames in os.walk(workspace_path):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    relative = os.path.relpath(full_path, workspace_path)

                    if any(fnmatch.fnmatch(relative, pat) for pat in patterns):
                        try:
                            with open(full_path) as fh:
                                results[relative] = fh.read()
                        except (OSError, UnicodeDecodeError) as exc:
                            logger.warning(
                                "file_read_error",
                                path=relative,
                                error=str(exc),
                            )

            logger.info(
                "outputs_collected",
                workspace_path=workspace_path,
                matched_files=len(results),
            )
            return results

        return await asyncio.to_thread(_collect)

    async def cleanup(self, workspace_path: str) -> None:
        """Remove *workspace_path* and all its contents.

        No-ops silently if the directory does not exist.
        """

        def _cleanup() -> None:
            if not os.path.isdir(workspace_path):
                return
            shutil.rmtree(workspace_path, ignore_errors=True)
            logger.info("workspace_cleaned", workspace_path=workspace_path)

        await asyncio.to_thread(_cleanup)
