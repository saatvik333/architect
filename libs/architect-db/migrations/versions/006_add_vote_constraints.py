"""Add FK and unique constraints to approval_votes.

Revision ID: 006
Revises: 005
"""

from alembic import op

revision = "006"
down_revision = "005"


def upgrade() -> None:
    op.create_foreign_key(
        "fk_approval_votes_gate_id",
        "approval_votes",
        "approval_gates",
        ["gate_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_approval_votes_gate_voter",
        "approval_votes",
        ["gate_id", "voter"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_approval_votes_gate_voter", "approval_votes", type_="unique")
    op.drop_constraint("fk_approval_votes_gate_id", "approval_votes", type_="foreignkey")
