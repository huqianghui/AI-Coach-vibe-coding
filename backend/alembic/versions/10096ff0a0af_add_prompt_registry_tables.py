"""add prompt registry tables

Revision ID: 10096ff0a0af
Revises: v29a_conference_prompt_config
Create Date: 2026-07-01 04:10:24.590751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10096ff0a0af'
down_revision: Union[str, None] = 'v29a_conference_prompt_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('prompt_templates',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('variables', sa.Text(), nullable=False),
    sa.Column('active_version_id', sa.String(length=36), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prompt_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prompt_templates_key'), ['key'], unique=True)

    op.create_table('prompt_versions',
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('parent_version_id', sa.String(length=36), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['prompt_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prompt_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prompt_versions_template_id'), ['template_id'], unique=False)

    op.create_table('prompt_optimization_runs',
    sa.Column('template_id', sa.String(length=36), nullable=False),
    sa.Column('base_version_id', sa.String(length=36), nullable=True),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('optimizer_template', sa.String(length=100), nullable=True),
    sa.Column('requirements', sa.Text(), nullable=True),
    sa.Column('result_content', sa.Text(), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('resulting_version_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['prompt_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prompt_optimization_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prompt_optimization_runs_template_id'), ['template_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('prompt_optimization_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prompt_optimization_runs_template_id'))
    op.drop_table('prompt_optimization_runs')

    with op.batch_alter_table('prompt_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prompt_versions_template_id'))
    op.drop_table('prompt_versions')

    with op.batch_alter_table('prompt_templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prompt_templates_key'))
    op.drop_table('prompt_templates')
