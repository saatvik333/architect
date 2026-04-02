"""Add pgvector embedding column to knowledge_entries.

Revision ID: 007
Revises: 006
"""

from alembic import op

revision = "007"
down_revision = "006"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS embedding_vec vector(384)")
    # Backfill from JSONB embedding column where possible
    op.execute("""
        UPDATE knowledge_entries
        SET embedding_vec = embedding::text::vector
        WHERE embedding IS NOT NULL
          AND embedding != 'null'
          AND jsonb_typeof(embedding) = 'array'
          AND jsonb_array_length(embedding) = 384
    """)
    # Create HNSW index for cosine distance
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_embedding_hnsw
        ON knowledge_entries
        USING hnsw (embedding_vec vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entries_embedding_hnsw")
    op.execute("ALTER TABLE knowledge_entries DROP COLUMN IF EXISTS embedding_vec")
