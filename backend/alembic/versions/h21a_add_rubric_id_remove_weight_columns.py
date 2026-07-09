"""add rubric_id to scenarios, migrate weight data to rubrics, remove weight columns

Revision ID: h21a00000001
Revises: q20a00000001
Create Date: 2026-04-27 15:00:00.000000

"""

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h21a00000001"
down_revision: str = "q20a00000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Detailed criteria from the existing SCORING_PROMPT_TEMPLATE (Pitfall #6)
CRITERIA_MAP = {
    "key_message": [
        "Consider which key messages were delivered and how naturally",
        "Evaluate completeness of message coverage",
        "Assess logical flow of message delivery",
    ],
    "objection_handling": [
        "Evaluate how the MR responded to HCP resistance or concerns",
        "Assess use of clinical evidence in responses",
        "Evaluate acknowledgment of HCP concerns before countering",
    ],
    "communication": [
        "Evaluate tone, active listening, professional language",
        "Assess adaptation to HCP communication style",
        "Evaluate use of reflective listening techniques",
    ],
    "product_knowledge": [
        "Evaluate accuracy and depth of product information shared",
        "Assess dosing and administration knowledge",
        "Evaluate competitive product comparison ability",
    ],
    "scientific_info": [
        "Evaluate use of clinical data, study references, and evidence-based arguments",
        "Assess ability to cite specific study names and endpoints",
        "Evaluate discussion of patient populations and outcomes",
    ],
}

DIM_NAMES = [
    "key_message",
    "objection_handling",
    "communication",
    "product_knowledge",
    "scientific_info",
]


def _get_rubric_created_by_user_id(conn) -> str | None:
    admin_row = conn.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    ).fetchone()
    if admin_row:
        return admin_row[0]

    scenario_user_row = conn.execute(
        sa.text(
            "SELECT s.created_by FROM scenarios s "
            "JOIN users u ON u.id = s.created_by "
            "WHERE s.created_by IS NOT NULL LIMIT 1"
        )
    ).fetchone()
    return scenario_user_row[0] if scenario_user_row else None


def upgrade() -> None:
    # -- Step 1: Add rubric_id column as NULLABLE (temporarily) --
    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.add_column(
            sa.Column(
                "rubric_id",
                sa.String(36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_scenarios_rubric_id",
            "scoring_rubrics",
            ["rubric_id"],
            ["id"],
        )

    # -- Step 2: Data migration -- create rubric per unique weight combo --
    conn = op.get_bind()
    now = datetime.now(UTC).replace(tzinfo=None)

    # Read all existing scenarios with their weight columns
    rows = conn.execute(
        sa.text(
            "SELECT id, weight_key_message, weight_objection_handling, "
            "weight_communication, weight_product_knowledge, weight_scientific_info "
            "FROM scenarios"
        )
    ).fetchall()

    # Group scenarios by unique weight combination
    weight_combos: dict[tuple, list[str]] = {}
    for row in rows:
        combo = (row[1], row[2], row[3], row[4], row[5])
        weight_combos.setdefault(combo, []).append(row[0])

    created_by_user_id = _get_rubric_created_by_user_id(conn)

    for combo, scenario_ids in weight_combos.items():
        if created_by_user_id is None:
            raise RuntimeError("Cannot create migrated scoring rubrics without an existing user")

        rubric_id = str(uuid.uuid4())
        is_default = combo == (30, 25, 20, 15, 10)

        # If marking this rubric as default, unset any existing defaults first
        if is_default:
            conn.execute(
                sa.text(
                    "UPDATE scoring_rubrics SET is_default = :new_default "
                    "WHERE scenario_type = 'f2f' AND is_default = :old_default"
                ),
                {"new_default": False, "old_default": True},
            )

        dims = json.dumps(
            [
                {
                    "name": DIM_NAMES[i],
                    "weight": combo[i],
                    "criteria": CRITERIA_MAP[DIM_NAMES[i]],
                    "max_score": 100.0,
                }
                for i in range(5)
            ]
        )
        rubric_name = (
            "Default Scoring Rubric"
            if is_default
            else f"Migrated Rubric ({'/'.join(str(w) for w in combo)})"
        )

        conn.execute(
            sa.text(
                "INSERT INTO scoring_rubrics (id, name, description, scenario_type, "
                "dimensions, is_default, created_by, created_at, updated_at) "
                "VALUES (:id, :name, :desc, :stype, :dims, :is_default, :created_by, :cat, :uat)"
            ),
            {
                "id": rubric_id,
                "name": rubric_name,
                "desc": "Auto-created from scenario weight columns during phase 21 migration",
                "stype": "f2f",
                "dims": dims,
                "is_default": is_default,
                "created_by": created_by_user_id,
                "cat": now,
                "uat": now,
            },
        )

        for sid in scenario_ids:
            conn.execute(
                sa.text("UPDATE scenarios SET rubric_id = :rid WHERE id = :sid"),
                {"rid": rubric_id, "sid": sid},
            )

    # -- Step 3: Enforce NOT NULL on rubric_id, then drop weight columns --
    # For scenarios that still have no rubric_id (edge case: empty DB or new rows),
    # find or create a default rubric to assign
    null_rows = conn.execute(sa.text("SELECT id FROM scenarios WHERE rubric_id IS NULL")).fetchall()
    if null_rows:
        default_row = conn.execute(
            sa.text(
                "SELECT id FROM scoring_rubrics WHERE is_default = :is_default "
                "AND scenario_type = 'f2f' LIMIT 1"
            ),
            {"is_default": True},
        ).fetchone()
        if default_row:
            fallback_rid = default_row[0]
        else:
            if created_by_user_id is None:
                raise RuntimeError("Cannot create fallback scoring rubric without an existing user")

            fallback_rid = str(uuid.uuid4())
            default_dims = json.dumps(
                [
                    {
                        "name": DIM_NAMES[i],
                        "weight": [30, 25, 20, 15, 10][i],
                        "criteria": CRITERIA_MAP[DIM_NAMES[i]],
                        "max_score": 100.0,
                    }
                    for i in range(5)
                ]
            )
            conn.execute(
                sa.text(
                    "INSERT INTO scoring_rubrics (id, name, description, scenario_type, "
                    "dimensions, is_default, created_by, created_at, updated_at) "
                    "VALUES (:id, :name, :desc, :stype, :dims, "
                    ":is_default, :created_by, :cat, :uat)"
                ),
                {
                    "id": fallback_rid,
                    "name": "Default Scoring Rubric",
                    "desc": "Auto-created during phase 21 migration (fallback)",
                    "stype": "f2f",
                    "dims": default_dims,
                    "is_default": True,
                    "created_by": created_by_user_id,
                    "cat": now,
                    "uat": now,
                },
            )
        for nr in null_rows:
            conn.execute(
                sa.text("UPDATE scenarios SET rubric_id = :rid WHERE id = :sid"),
                {"rid": fallback_rid, "sid": nr[0]},
            )

    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.alter_column("rubric_id", nullable=False)
        batch_op.drop_column("weight_key_message")
        batch_op.drop_column("weight_objection_handling")
        batch_op.drop_column("weight_communication")
        batch_op.drop_column("weight_product_knowledge")
        batch_op.drop_column("weight_scientific_info")


def downgrade() -> None:
    # Restore weight columns with default values
    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.add_column(
            sa.Column("weight_key_message", sa.Integer(), server_default="30", nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_objection_handling", sa.Integer(), server_default="25", nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_communication", sa.Integer(), server_default="20", nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_product_knowledge", sa.Integer(), server_default="15", nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_scientific_info", sa.Integer(), server_default="10", nullable=True)
        )

    # Restore weights from linked rubric dimensions
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT s.id, r.dimensions FROM scenarios s "
            "JOIN scoring_rubrics r ON s.rubric_id = r.id"
        )
    ).fetchall()
    for row in rows:
        dims = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        weight_map = {d["name"]: d["weight"] for d in dims}
        conn.execute(
            sa.text(
                "UPDATE scenarios SET "
                "weight_key_message = :wk, weight_objection_handling = :wo, "
                "weight_communication = :wc, weight_product_knowledge = :wp, "
                "weight_scientific_info = :ws "
                "WHERE id = :sid"
            ),
            {
                "sid": row[0],
                "wk": weight_map.get("key_message", 30),
                "wo": weight_map.get("objection_handling", 25),
                "wc": weight_map.get("communication", 20),
                "wp": weight_map.get("product_knowledge", 15),
                "ws": weight_map.get("scientific_info", 10),
            },
        )

    # Drop rubric_id column
    with op.batch_alter_table("scenarios") as batch_op:
        batch_op.drop_column("rubric_id")
