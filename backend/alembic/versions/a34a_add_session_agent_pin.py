"""Add immutable Foundry Agent pin fields to coaching sessions.

Revision ID: a34a_session_agent_pin
Revises: z33a_drop_hcp_voice_fields
Create Date: 2026-07-25
"""

import sqlalchemy as sa

from alembic import op

revision = "a34a_session_agent_pin"
down_revision = "z33a_drop_hcp_voice_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable pins without guessing identity for historical sessions."""
    with op.batch_alter_table("coaching_sessions") as batch_op:
        batch_op.add_column(sa.Column("agent_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("agent_version", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("agent_response_id", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove only the Foundry Agent pin fields."""
    with op.batch_alter_table("coaching_sessions") as batch_op:
        batch_op.drop_column("agent_response_id")
        batch_op.drop_column("agent_version")
        batch_op.drop_column("agent_name")
