"""Add Phase 4 tables for Security Immune, Failure Taxonomy, and Deployment Pipeline.

Revision ID: 010_add_phase4_tables
Revises: 009_enum_columns
Create Date: 2026-04-02

Creates 7 tables:
- Security Immune: security_scans, security_findings, security_policies
- Failure Taxonomy: failure_records, post_mortems, improvements, simulation_runs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "010_add_phase4_tables"
down_revision: str | None = "009_enum_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Security Immune ──────────────────────────────────────────
    op.create_table(
        "security_scans",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("scan_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_security_scans_scan_type", "security_scans", ["scan_type"])
    op.create_index("ix_security_scans_target_id", "security_scans", ["target_id"])
    op.create_index("ix_security_scans_created_at", "security_scans", ["created_at"])

    op.create_table(
        "security_findings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "scan_id",
            sa.Text(),
            sa.ForeignKey("security_scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("cwe_id", sa.Text(), nullable=True),
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
    op.create_index("ix_security_findings_scan_id", "security_findings", ["scan_id"])
    op.create_index("ix_security_findings_severity", "security_findings", ["severity"])
    op.create_index("ix_security_findings_status", "security_findings", ["status"])

    op.create_table(
        "security_policies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("scan_type", sa.Text(), nullable=False),
        sa.Column("rules", JSONB, nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_security_policies_scan_type", "security_policies", ["scan_type"])

    # ── Failure Taxonomy ─────────────────────────────────────────
    op.create_table(
        "failure_records",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("eval_layer", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("classified_by", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_failure_records_task_id", "failure_records", ["task_id"])
    op.create_index("ix_failure_records_project_id", "failure_records", ["project_id"])
    op.create_index("ix_failure_records_failure_code", "failure_records", ["failure_code"])
    op.create_index("ix_failure_records_created_at", "failure_records", ["created_at"])

    op.create_table(
        "post_mortems",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_breakdown", JSONB, nullable=True),
        sa.Column("root_causes", JSONB, nullable=True),
        sa.Column("prompt_improvements", JSONB, nullable=True),
        sa.Column("new_adversarial_tests", JSONB, nullable=True),
        sa.Column("heuristic_updates", JSONB, nullable=True),
        sa.Column("topology_recommendations", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_post_mortems_project_id", "post_mortems", ["project_id"])

    op.create_table(
        "improvements",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "post_mortem_id",
            sa.Text(),
            sa.ForeignKey("post_mortems.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("improvement_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content", JSONB, nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_improvements_post_mortem_id", "improvements", ["post_mortem_id"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("failures_injected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failures_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detection_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("results", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("simulation_runs")
    op.drop_table("improvements")
    op.drop_table("post_mortems")
    op.drop_table("failure_records")
    op.drop_table("security_policies")
    op.drop_table("security_findings")
    op.drop_table("security_scans")
