"""Add Phase 3 tables for Knowledge & Memory, Economic Governor, and Human Interface.

Revision ID: 005_add_phase3_tables
Revises: 004_add_ledger_delta_columns
Create Date: 2026-03-24

Creates 10 tables:
- Knowledge & Memory: knowledge_entries, knowledge_observations, heuristic_rules, meta_strategies
- Economic Governor: budget_records, agent_efficiency_scores, enforcement_actions
- Human Interface: escalations, approval_gates, approval_votes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "005_add_phase3_tables"
down_revision: str | None = "004_add_ledger_delta_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Knowledge & Memory ────────────────────────────────────────
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("version_tag", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column("parent_id", sa.Text(), sa.ForeignKey("knowledge_entries.id"), nullable=True),
        sa.Column("superseded_by", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_knowledge_entries_layer", "knowledge_entries", ["layer"])
    op.create_index("ix_knowledge_entries_topic", "knowledge_entries", ["topic"])

    op.create_table(
        "knowledge_observations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("observation_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("outcome", JSONB, nullable=True),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column(
            "compressed_into",
            sa.Text(),
            sa.ForeignKey("knowledge_entries.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_knowledge_observations_task_id", "knowledge_observations", ["task_id"])

    op.create_table(
        "heuristic_rules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("condition_structured", JSONB, nullable=True),
        sa.Column("action_structured", JSONB, nullable=True),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("source_patterns", JSONB, nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
    op.create_index("ix_heuristic_rules_domain", "heuristic_rules", ["domain"])

    op.create_table(
        "meta_strategies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("strategy_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("config_patch", JSONB, nullable=True),
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="'proposed'"),
        sa.Column("effectiveness_score", sa.Float(), nullable=True),
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

    # ── Economic Governor ─────────────────────────────────────────
    op.create_table(
        "budget_records",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("allocated_tokens", sa.Integer(), nullable=False),
        sa.Column("consumed_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allocated_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("consumed_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("burn_rate_tokens_per_min", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("enforcement_level", sa.Text(), nullable=False, server_default="'none'"),
        sa.Column("phase_breakdown", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_budget_records_project_id", "budget_records", ["project_id"])

    op.create_table(
        "agent_efficiency_scores",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.Text(), nullable=False),
        sa.Column("model_tier", sa.Text(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("average_quality_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("efficiency_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_efficiency_scores_agent_id", "agent_efficiency_scores", ["agent_id"])

    op.create_table(
        "enforcement_actions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("enforcement_level", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("budget_consumed_pct", sa.Float(), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── Human Interface ───────────────────────────────────────────
    op.create_table(
        "escalations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("source_agent_id", sa.Text(), nullable=True),
        sa.Column("source_task_id", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("recommended_option", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("risk_if_wrong", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="'pending'"),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolution_details", JSONB, nullable=True),
        sa.Column("decision_confidence", sa.Float(), nullable=True),
        sa.Column("is_security_critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cost_impact_pct", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_escalations_status", "escalations", ["status"])
    op.create_index("ix_escalations_created_at", "escalations", ["created_at"])
    op.create_index("ix_escalations_category", "escalations", ["category"])

    op.create_table(
        "approval_gates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="'pending'"),
        sa.Column("context", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approval_gates_status", "approval_gates", ["status"])
    op.create_index("ix_approval_gates_action_type", "approval_gates", ["action_type"])

    op.create_table(
        "approval_votes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("gate_id", sa.Text(), nullable=False),
        sa.Column("voter", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_approval_votes_gate_id", "approval_votes", ["gate_id"])


def downgrade() -> None:
    # Human Interface
    op.drop_table("approval_votes")
    op.drop_table("approval_gates")
    op.drop_table("escalations")
    # Economic Governor
    op.drop_table("enforcement_actions")
    op.drop_table("agent_efficiency_scores")
    op.drop_table("budget_records")
    # Knowledge & Memory
    op.drop_table("meta_strategies")
    op.drop_table("heuristic_rules")
    op.drop_table("knowledge_observations")
    op.drop_table("knowledge_entries")
