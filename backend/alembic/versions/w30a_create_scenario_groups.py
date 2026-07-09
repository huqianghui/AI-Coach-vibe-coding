"""Create scenario group tables.

Revision ID: w30a_create_scenario_groups
Revises: v29a_conference_prompt_config
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "w30a_create_scenario_groups"
down_revision: str | None = "v29a_conference_prompt_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_groups",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("pass_threshold", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenario_groups_status", "scenario_groups", ["status"])

    op.create_table(
        "scenario_group_items",
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["group_id"], ["scenario_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "scenario_id", name="uq_scenario_group_items_group_scenario"
        ),
    )
    op.create_index("ix_scenario_group_items_group_id", "scenario_group_items", ["group_id"])
    op.create_index(
        "ix_scenario_group_items_group_order",
        "scenario_group_items",
        ["group_id", "sort_order"],
    )
    op.create_index("ix_scenario_group_items_scenario_id", "scenario_group_items", ["scenario_id"])

    op.create_table(
        "scenario_group_runs",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["group_id"], ["scenario_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenario_group_runs_group", "scenario_group_runs", ["group_id"])
    op.create_index(
        "ix_scenario_group_runs_user_status",
        "scenario_group_runs",
        ["user_id", "status"],
    )

    op.create_table(
        "scenario_group_run_items",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("group_item_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["group_item_id"], ["scenario_group_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["scenario_group_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["coaching_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "group_item_id", name="uq_scenario_group_run_items_run_item"),
    )
    op.create_index("ix_scenario_group_run_items_run_id", "scenario_group_run_items", ["run_id"])
    op.create_index(
        "ix_scenario_group_run_items_run_order",
        "scenario_group_run_items",
        ["run_id", "sort_order"],
    )
    op.create_index(
        "ix_scenario_group_run_items_scenario_id", "scenario_group_run_items", ["scenario_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_group_run_items_scenario_id", table_name="scenario_group_run_items")
    op.drop_index("ix_scenario_group_run_items_run_order", table_name="scenario_group_run_items")
    op.drop_index("ix_scenario_group_run_items_run_id", table_name="scenario_group_run_items")
    op.drop_table("scenario_group_run_items")

    op.drop_index("ix_scenario_group_runs_user_status", table_name="scenario_group_runs")
    op.drop_index("ix_scenario_group_runs_group", table_name="scenario_group_runs")
    op.drop_table("scenario_group_runs")

    op.drop_index("ix_scenario_group_items_scenario_id", table_name="scenario_group_items")
    op.drop_index("ix_scenario_group_items_group_order", table_name="scenario_group_items")
    op.drop_index("ix_scenario_group_items_group_id", table_name="scenario_group_items")
    op.drop_table("scenario_group_items")

    op.drop_index("ix_scenario_groups_status", table_name="scenario_groups")
    op.drop_table("scenario_groups")
