"""Add event_log timestamp index for time-range queries.

Revision ID: 003_add_indexes_and_fk
Revises: 002_add_fk_constraints
Create Date: 2026-03-15

Note: Composite index on proposals(verdict, created_at) and index on
evaluation_reports(verdict) were already added in migration 002.  FK
constraints on proposals and event_log were also covered by 002.  This
migration adds the remaining index on event_log(timestamp) — the column
was created in 001 with ``index=True`` in the ORM model, but the explicit
index ``ix_event_log_timestamp`` already exists from 001.  We add a
covering index on event_log(timestamp, type) to accelerate combined
time-range + type filtering and an index on event_log(created_at) — if a
``created_at`` column is later added — is omitted because the ORM model
uses ``timestamp`` for that purpose.

The only net-new object here is a composite index useful for the common
"events by type within a time window" access pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_indexes_and_fk"
down_revision: str | None = "002_add_fk_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Composite index for time-range + type queries on event_log ──
    op.create_index(
        "ix_event_log_timestamp_type",
        "event_log",
        ["timestamp", "type"],
    )

    # ── FK: evaluation_reports.agent_id → agent_sessions.id ─────────
    # evaluation_reports.task_id and .sandbox_session_id FKs were
    # created inline in 001_initial.  agent_id was left as a plain
    # text column — add the constraint now.
    op.create_foreign_key(
        "fk_evaluation_reports_agent_id",
        "evaluation_reports",
        "agent_sessions",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_evaluation_reports_agent_id",
        "evaluation_reports",
        type_="foreignkey",
    )
    op.drop_index("ix_event_log_timestamp_type", table_name="event_log")
