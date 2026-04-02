"""Migrate enum-like Text columns to VARCHAR(64) for sa.Enum(native_enum=False).

Revision ID: 009_enum_columns
Revises: 008_add_observation_indexes
"""

from alembic import op

revision = "009_enum_columns"
down_revision = "008_add_observation_indexes"


def upgrade() -> None:
    # Escalation model
    op.execute("ALTER TABLE escalations ALTER COLUMN category TYPE VARCHAR(64)")
    op.execute("ALTER TABLE escalations ALTER COLUMN severity TYPE VARCHAR(64)")
    op.execute("ALTER TABLE escalations ALTER COLUMN status TYPE VARCHAR(64)")

    # ApprovalGate model
    op.execute("ALTER TABLE approval_gates ALTER COLUMN status TYPE VARCHAR(64)")

    # KnowledgeEntry model
    op.execute("ALTER TABLE knowledge_entries ALTER COLUMN layer TYPE VARCHAR(64)")
    op.execute("ALTER TABLE knowledge_entries ALTER COLUMN content_type TYPE VARCHAR(64)")

    # KnowledgeObservation model
    op.execute("ALTER TABLE knowledge_observations ALTER COLUMN observation_type TYPE VARCHAR(64)")


def downgrade() -> None:
    # Revert to TEXT
    op.execute("ALTER TABLE escalations ALTER COLUMN category TYPE TEXT")
    op.execute("ALTER TABLE escalations ALTER COLUMN severity TYPE TEXT")
    op.execute("ALTER TABLE escalations ALTER COLUMN status TYPE TEXT")

    op.execute("ALTER TABLE approval_gates ALTER COLUMN status TYPE TEXT")

    op.execute("ALTER TABLE knowledge_entries ALTER COLUMN layer TYPE TEXT")
    op.execute("ALTER TABLE knowledge_entries ALTER COLUMN content_type TYPE TEXT")

    op.execute("ALTER TABLE knowledge_observations ALTER COLUMN observation_type TYPE TEXT")
