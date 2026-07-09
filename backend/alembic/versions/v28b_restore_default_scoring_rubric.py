"""Restore default F2F scoring rubric if missing.

Revision ID: v28b_restore_default_rubric
Revises: v28a_scoring_prompt_template
Create Date: 2026-06-25
"""

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "v28b_restore_default_rubric"
down_revision: str | None = "v28a_scoring_prompt_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_DIMENSIONS = [
    {
        "name": "key_message",
        "weight": 25,
        "criteria": [
            "Consider which key messages were delivered and how naturally",
            "Evaluate completeness of message coverage",
            "Assess logical flow of message delivery",
        ],
        "max_score": 100.0,
    },
    {
        "name": "objection_handling",
        "weight": 20,
        "criteria": [
            "Evaluate how the MR responded to HCP resistance or concerns",
            "Assess use of clinical evidence in responses",
            "Evaluate acknowledgment of HCP concerns before countering",
        ],
        "max_score": 100.0,
    },
    {
        "name": "communication",
        "weight": 20,
        "criteria": [
            "Evaluate tone, active listening, professional language",
            "Assess adaptation to HCP communication style",
            "Evaluate use of reflective listening techniques",
        ],
        "max_score": 100.0,
    },
    {
        "name": "product_knowledge",
        "weight": 20,
        "criteria": [
            "Evaluate accuracy and depth of product information shared",
            "Assess dosing and administration knowledge",
            "Evaluate competitive product comparison ability",
        ],
        "max_score": 100.0,
    },
    {
        "name": "scientific_info",
        "weight": 15,
        "criteria": [
            "Evaluate use of clinical data, study references, and evidence-based arguments",
            "Assess ability to cite specific study names and endpoints",
            "Evaluate discussion of patient populations and outcomes",
        ],
        "max_score": 100.0,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text(
            "SELECT id FROM scoring_rubrics "
            "WHERE scenario_type = 'f2f' AND is_default = :is_default LIMIT 1"
        ),
        {"is_default": True},
    ).fetchone()
    if existing:
        return

    admin_row = conn.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    ).fetchone()
    if admin_row is None:
        return
    admin_id = admin_row[0]
    now = datetime.now(UTC).replace(tzinfo=None)
    conn.execute(
        sa.text(
            "INSERT INTO scoring_rubrics ("
            "id, name, description, scenario_type, dimensions, prompt_template, prompt_version, "
            "is_default, content_weight, voice_weight, created_by, created_at, updated_at"
            ") VALUES ("
            ":id, :name, :description, :scenario_type, :dimensions, :prompt_template, "
            ":prompt_version, :is_default, :content_weight, :voice_weight, :created_by, "
            ":created_at, :updated_at"
            ")"
        ),
        {
            "id": str(uuid.uuid4()),
            "name": "Default F2F Scoring Rubric",
            "description": "Standard 5-dimension scoring rubric for F2F coaching sessions",
            "scenario_type": "f2f",
            "dimensions": json.dumps(DEFAULT_DIMENSIONS),
            "prompt_template": "",
            "prompt_version": 1,
            "is_default": True,
            "content_weight": 60,
            "voice_weight": 40,
            "created_by": admin_id,
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM scoring_rubrics "
            "WHERE name = 'Default F2F Scoring Rubric' "
            "AND scenario_type = 'f2f' AND is_default = :is_default"
        ),
        {"is_default": True},
    )
