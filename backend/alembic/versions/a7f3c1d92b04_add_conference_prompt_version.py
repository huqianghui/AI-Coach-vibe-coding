"""add conference_prompt_version to scenarios

Revision ID: a7f3c1d92b04
Revises: 10096ff0a0af
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3c1d92b04'
down_revision: Union[str, None] = '10096ff0a0af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'conference_prompt_version',
                sa.Integer(),
                nullable=False,
                server_default='1',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('conference_prompt_version')
