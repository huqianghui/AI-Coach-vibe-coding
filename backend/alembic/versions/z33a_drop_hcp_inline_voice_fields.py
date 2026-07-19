"""Drop deprecated inline voice/avatar columns from hcp_profiles (D-09).

HCP voice/avatar config now comes exclusively from the VoiceLiveInstance
FK (voice_live_instance_id). No backfill -- inline values are discarded
per explicit user decision (D-09/D-10). downgrade() re-adds the columns
with their original defaults but CANNOT restore per-row data.

Revision ID: z33a_drop_hcp_voice_fields
Revises: y32a_skill_foundry_sync
Create Date: 2026-07-19
"""

import sqlalchemy as sa

from alembic import op

revision = "z33a_drop_hcp_voice_fields"
down_revision = "y32a_skill_foundry_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hcp_profiles") as batch_op:
        batch_op.drop_column("voice_live_enabled")
        batch_op.drop_column("voice_live_model")
        batch_op.drop_column("voice_name")
        batch_op.drop_column("voice_type")
        batch_op.drop_column("voice_temperature")
        batch_op.drop_column("voice_custom")
        batch_op.drop_column("avatar_character")
        batch_op.drop_column("avatar_style")
        batch_op.drop_column("avatar_customized")
        batch_op.drop_column("turn_detection_type")
        batch_op.drop_column("noise_suppression")
        batch_op.drop_column("echo_cancellation")
        batch_op.drop_column("eou_detection")
        batch_op.drop_column("recognition_language")


def downgrade() -> None:
    # NOTE: restores columns with their original defaults only -- per-row
    # data discarded by upgrade() is NOT recoverable (accepted risk, D-09).
    with op.batch_alter_table("hcp_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("voice_live_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("voice_live_model", sa.String(50), nullable=False, server_default="gpt-4o")
        )
        batch_op.add_column(
            sa.Column(
                "voice_name", sa.String(200), nullable=False, server_default="en-US-AvaNeural"
            )
        )
        batch_op.add_column(
            sa.Column("voice_type", sa.String(50), nullable=False, server_default="azure-standard")
        )
        batch_op.add_column(
            sa.Column("voice_temperature", sa.Float(), nullable=False, server_default="0.9")
        )
        batch_op.add_column(
            sa.Column("voice_custom", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("avatar_character", sa.String(100), nullable=False, server_default="lori")
        )
        batch_op.add_column(
            sa.Column("avatar_style", sa.String(100), nullable=False, server_default="casual")
        )
        batch_op.add_column(
            sa.Column("avatar_customized", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column(
                "turn_detection_type", sa.String(50), nullable=False, server_default="server_vad"
            )
        )
        batch_op.add_column(
            sa.Column("noise_suppression", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("echo_cancellation", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("eou_detection", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("recognition_language", sa.String(20), nullable=False, server_default="auto")
        )
