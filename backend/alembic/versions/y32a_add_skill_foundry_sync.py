"""Add Skill Foundry sync tracking columns (Phase 28: D-01, D-03, D-06).

Revision ID: y32a_skill_foundry_sync
Revises: x31a_merge_heads
Create Date: 2026-07-18
"""

import sqlalchemy as sa

from alembic import op

revision = "y32a_skill_foundry_sync"
down_revision = "x31a_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("skills") as batch_op:
        batch_op.add_column(
            sa.Column("foundry_skill_name", sa.String(64), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("foundry_sync_status", sa.String(20), nullable=False, server_default="none")
        )
        batch_op.add_column(
            sa.Column("foundry_sync_error", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("foundry_cloud_version", sa.String(20), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("skills") as batch_op:
        batch_op.drop_column("foundry_cloud_version")
        batch_op.drop_column("foundry_sync_error")
        batch_op.drop_column("foundry_sync_status")
        batch_op.drop_column("foundry_skill_name")
