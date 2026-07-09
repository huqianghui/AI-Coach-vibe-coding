"""Merge prompt registry and scenario group migration heads.

Revision ID: x31a_merge_heads
Revises: a7f3c1d92b04, w30a_create_scenario_groups
Create Date: 2026-07-09
"""

from collections.abc import Sequence

revision: str = "x31a_merge_heads"
down_revision: tuple[str, str] = ("a7f3c1d92b04", "w30a_create_scenario_groups")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
