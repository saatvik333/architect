"""Verify Alembic migration chain integrity.

Tests that all migration files have required metadata and form a valid
linear revision chain without breaks or orphans.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations" / "versions"

# Regex patterns to extract revision/down_revision from migration files.
# These handle both single-quoted and double-quoted string literals, as well
# as the Python literal ``None``.
_REVISION_RE = re.compile(
    r"^revision(?:\s*:\s*\w[\w\s|]*?)?\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE
)
_DOWN_REVISION_RE = re.compile(
    r"^down_revision(?:\s*:\s*[\w\s|]*?)?\s*=\s*(?:None|['\"]([^'\"]*)['\"])",
    re.MULTILINE,
)


def _migration_files() -> list[Path]:
    """Return sorted list of migration .py files, excluding __pycache__ and .gitkeep."""
    return sorted(p for p in MIGRATIONS_DIR.glob("*.py") if p.name != "__init__.py")


class TestMigrationChain:
    """Ensure that the Alembic migration chain is well-formed."""

    def test_migrations_directory_exists(self) -> None:
        """The migrations/versions directory must exist."""
        assert MIGRATIONS_DIR.is_dir(), f"Missing migrations directory: {MIGRATIONS_DIR}"

    def test_at_least_one_migration_exists(self) -> None:
        """There must be at least one migration file."""
        files = _migration_files()
        assert len(files) > 0, "No migration files found"

    def test_all_migrations_have_revision_ids(self) -> None:
        """Every migration file must define revision and down_revision."""
        for mf in _migration_files():
            content = mf.read_text()
            assert "revision" in content, f"{mf.name} missing revision"
            assert "down_revision" in content, f"{mf.name} missing down_revision"

    def test_all_migrations_have_upgrade_downgrade(self) -> None:
        """Every migration file must define upgrade() and downgrade() functions."""
        for mf in _migration_files():
            content = mf.read_text()
            assert "def upgrade" in content, f"{mf.name} missing upgrade()"
            assert "def downgrade" in content, f"{mf.name} missing downgrade()"

    def test_revision_ids_are_unique(self) -> None:
        """No two migrations should share the same revision id."""
        seen: dict[str, str] = {}
        for mf in _migration_files():
            content = mf.read_text()
            match = _REVISION_RE.search(content)
            if match is None:
                continue
            rev = match.group(1)
            assert rev not in seen, f"Duplicate revision {rev!r} in {mf.name} and {seen[rev]}"
            seen[rev] = mf.name

    def test_migration_chain_is_linear(self) -> None:
        """Each migration's down_revision must reference an existing revision.

        Exactly one migration should have down_revision = None (the initial migration).
        """
        revisions: dict[str, str | None] = {}

        for mf in _migration_files():
            content = mf.read_text()

            rev_match = _REVISION_RE.search(content)
            assert rev_match is not None, f"{mf.name}: could not parse revision"
            rev = rev_match.group(1)

            down_match = _DOWN_REVISION_RE.search(content)
            if down_match is None:
                # down_revision = None (no capture group)
                down_rev = None
            else:
                down_rev = down_match.group(1) if down_match.group(1) else None

            revisions[rev] = down_rev

        # Verify chain integrity
        roots = [rev for rev, down in revisions.items() if down is None]
        assert len(roots) == 1, (
            f"Expected exactly one root migration (down_revision=None), found {len(roots)}: {roots}"
        )

        for rev, down_rev in revisions.items():
            if down_rev is None:
                continue
            assert down_rev in revisions, (
                f"Broken chain: revision {rev} references down_revision {down_rev!r} "
                f"which does not exist"
            )

    def test_no_migration_references_itself(self) -> None:
        """A migration's down_revision must not equal its own revision."""
        for mf in _migration_files():
            content = mf.read_text()
            rev_match = _REVISION_RE.search(content)
            down_match = _DOWN_REVISION_RE.search(content)

            if rev_match and down_match and down_match.group(1):
                assert rev_match.group(1) != down_match.group(1), (
                    f"{mf.name}: revision references itself"
                )
