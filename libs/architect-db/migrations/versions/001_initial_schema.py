"""Initial schema — all Phase 1 and Phase 2 tables.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-15

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── tasks ────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("agent_type", sa.Text, nullable=True),
        sa.Column("model_tier", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dependencies", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("dependents", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("inputs", postgresql.JSONB, nullable=True),
        sa.Column("outputs", postgresql.JSONB, nullable=True),
        sa.Column("budget", postgresql.JSONB, nullable=True),
        sa.Column("assigned_agent", sa.Text, nullable=True),
        sa.Column("current_attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retry_history", postgresql.JSONB, nullable=True),
        sa.Column("verdict", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])

    # ── proposals ────────────────────────────────────────────────────
    op.create_table(
        "proposals",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("task_id", sa.Text, nullable=True),
        sa.Column("mutations", postgresql.JSONB, nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("verdict", sa.Text, nullable=False, server_default="pending"),
        sa.Column("verdict_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("verdict_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ledger_version_before", sa.BigInteger, nullable=True),
        sa.Column("ledger_version_after", sa.BigInteger, nullable=True),
    )

    # ── world_state_ledger ───────────────────────────────────────────
    op.create_table(
        "world_state_ledger",
        sa.Column("version", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("state_snapshot", postgresql.JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "proposal_id",
            sa.Text,
            sa.ForeignKey("proposals.id"),
            nullable=True,
        ),
    )

    # ── event_log ────────────────────────────────────────────────────
    op.create_table(
        "event_log",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ledger_version", sa.BigInteger, nullable=True),
        sa.Column("proposal_id", sa.Text, nullable=True),
        sa.Column("task_id", sa.Text, nullable=True),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, unique=True, nullable=True),
    )
    op.create_index("ix_event_log_type", "event_log", ["type"])
    op.create_index("ix_event_log_timestamp", "event_log", ["timestamp"])
    op.create_index("ix_event_log_task_id", "event_log", ["task_id"])
    op.create_index("ix_event_log_agent_id", "event_log", ["agent_id"])

    # ── sandbox_sessions ─────────────────────────────────────────────
    op.create_table(
        "sandbox_sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="creating"),
        sa.Column("container_id", sa.Text, nullable=True),
        sa.Column("image", sa.Text, nullable=True),
        sa.Column("resource_limits", postgresql.JSONB, nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("exit_code", sa.Integer, nullable=True),
    )
    op.create_index("ix_sandbox_sessions_status", "sandbox_sessions", ["status"])

    # ── sandbox_audit_log ────────────────────────────────────────────
    op.create_table(
        "sandbox_audit_log",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "session_id",
            sa.Text,
            sa.ForeignKey("sandbox_sessions.id"),
            nullable=False,
        ),
        sa.Column("command", sa.Text, nullable=False),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("stdout", sa.Text, nullable=True),
        sa.Column("stderr", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_sandbox_audit_log_session_id", "sandbox_audit_log", ["session_id"])

    # ── evaluation_reports ───────────────────────────────────────────
    op.create_table(
        "evaluation_reports",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "sandbox_session_id",
            sa.Text,
            sa.ForeignKey("sandbox_sessions.id"),
            nullable=True,
        ),
        sa.Column("agent_id", sa.Text, nullable=True),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("layers_run", sa.Integer, nullable=False, server_default="0"),
        sa.Column("layer_results", postgresql.JSONB, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("score", postgresql.JSONB, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evaluation_reports_task_id", "evaluation_reports", ["task_id"])

    # ── agent_sessions ───────────────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("agent_type", sa.Text, nullable=False),
        sa.Column("model_tier", sa.Text, nullable=False),
        sa.Column("current_task", sa.Text, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column("tokens_consumed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])

    # ── specifications (Phase 2) ─────────────────────────────────────
    op.create_table(
        "specifications",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("constraints", postgresql.JSONB, nullable=True),
        sa.Column("success_criteria", postgresql.JSONB, nullable=True),
        sa.Column("file_targets", postgresql.JSONB, nullable=True),
        sa.Column("assumptions", postgresql.JSONB, nullable=True),
        sa.Column("open_questions", postgresql.JSONB, nullable=True),
        sa.Column("stakeholder_review", postgresql.JSONB, nullable=True),
        sa.Column("scope_report", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_specifications_status", "specifications", ["status"])


def downgrade() -> None:
    op.drop_table("specifications")
    op.drop_table("agent_sessions")
    op.drop_table("evaluation_reports")
    op.drop_table("sandbox_audit_log")
    op.drop_table("sandbox_sessions")
    op.drop_table("event_log")
    op.drop_table("world_state_ledger")
    op.drop_table("proposals")
    op.drop_table("tasks")
