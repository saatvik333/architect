"""Add foreign-key constraints and missing indexes.

Revision ID: 002_add_fk_constraints
Revises: 001_initial
Create Date: 2026-03-15

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_fk_constraints"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Foreign keys on proposals ─────────────────────────────────────
    op.create_foreign_key(
        "fk_proposals_task_id",
        "proposals",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_proposals_agent_id",
        "proposals",
        "agent_sessions",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Foreign keys on event_log ─────────────────────────────────────
    op.create_foreign_key(
        "fk_event_log_task_id",
        "event_log",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_event_log_agent_id",
        "event_log",
        "agent_sessions",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_event_log_proposal_id",
        "event_log",
        "proposals",
        ["proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Missing indexes ───────────────────────────────────────────────
    op.create_index(
        "ix_proposals_verdict_created_at",
        "proposals",
        ["verdict", "created_at"],
    )
    op.create_index(
        "ix_evaluation_reports_verdict",
        "evaluation_reports",
        ["verdict"],
    )
    # ix_tasks_status already exists from 001_initial


def downgrade() -> None:
    # ── Drop indexes ──────────────────────────────────────────────────
    op.drop_index("ix_evaluation_reports_verdict", table_name="evaluation_reports")
    op.drop_index("ix_proposals_verdict_created_at", table_name="proposals")

    # ── Drop foreign keys on event_log ────────────────────────────────
    op.drop_constraint("fk_event_log_proposal_id", "event_log", type_="foreignkey")
    op.drop_constraint("fk_event_log_agent_id", "event_log", type_="foreignkey")
    op.drop_constraint("fk_event_log_task_id", "event_log", type_="foreignkey")

    # ── Drop foreign keys on proposals ────────────────────────────────
    op.drop_constraint("fk_proposals_agent_id", "proposals", type_="foreignkey")
    op.drop_constraint("fk_proposals_task_id", "proposals", type_="foreignkey")
