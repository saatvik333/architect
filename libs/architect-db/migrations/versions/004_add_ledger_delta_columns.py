"""Add mutations and is_checkpoint columns to world_state_ledger.

Revision ID: 004_add_ledger_delta_columns
Revises: 003_add_indexes_and_fk
Create Date: 2026-03-20

Adds delta-based storage support to the world_state_ledger table.
- ``mutations`` (JSONB, nullable) stores the list of mutations that produced
  each version.
- ``is_checkpoint`` (boolean, NOT NULL) marks whether the row carries a full
  ``state_snapshot``.

Existing rows are marked as checkpoints (``server_default='true'``) because
they all contain full snapshots.  The ORM model default for new rows is
``false``; only every Nth version is a checkpoint going forward.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "004_add_ledger_delta_columns"
down_revision: str | None = "003_add_indexes_and_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("world_state_ledger", sa.Column("mutations", JSONB, nullable=True))
    op.add_column(
        "world_state_ledger",
        sa.Column("is_checkpoint", sa.Boolean(), server_default="true", nullable=False),
    )
    # All existing rows have full snapshots, so server_default='true' marks
    # them as checkpoints automatically.


def downgrade() -> None:
    op.drop_column("world_state_ledger", "is_checkpoint")
    op.drop_column("world_state_ledger", "mutations")
