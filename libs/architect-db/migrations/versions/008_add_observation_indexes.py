"""Add indexes on observations table for compression pipeline.

Revision ID: 008
Revises: 007
"""

from alembic import op

revision = "008"
down_revision = "007"


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_observations_uncompressed
        ON observations (created_at)
        WHERE compressed = false
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_observations_domain ON observations (domain)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_observations_uncompressed")
    op.execute("DROP INDEX IF EXISTS ix_observations_domain")
