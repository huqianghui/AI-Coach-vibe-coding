"""Add Phase 31 Session context, Conversation lifecycle, and turn outbox.

Revision ID: b35a_phase31_turn_outbox
Revises: a34a_session_agent_pin
Create Date: 2026-08-05
"""

import sqlalchemy as sa

from alembic import op

revision = "b35a_phase31_turn_outbox"
down_revision = "a34a_session_agent_pin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add durable Session context and crash-safe provider orchestration state."""
    with op.batch_alter_table("coaching_sessions") as batch_op:
        batch_op.add_column(sa.Column("sop_snapshot_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("sop_snapshot_sha256", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("context_revision", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("foundry_conversation_id", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "foundry_conversation_state",
                sa.String(32),
                nullable=False,
                server_default="unprovisioned",
            )
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_create_operation_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_create_idempotency_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_create_lease_token", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_create_lease_expires_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_delete_lease_token", sa.String(64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_delete_lease_expires_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "foundry_conversation_create_retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "foundry_conversation_cleanup_retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_next_cleanup_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_last_error", sa.String(500), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_created_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_cleanup_started_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("foundry_conversation_closed_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_sessions_foundry_conversation_state",
            "foundry_conversation_state IN "
            "('unprovisioned', 'creating', 'active', 'create_unknown', "
            "'cleanup_pending', 'closed')",
        )
        batch_op.create_check_constraint(
            "ck_sessions_conversation_create_retries_nonnegative",
            "foundry_conversation_create_retry_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_sessions_conversation_cleanup_retries_nonnegative",
            "foundry_conversation_cleanup_retry_count >= 0",
        )
        batch_op.create_check_constraint(
            "ck_sessions_context_revision_nonnegative", "context_revision >= 0"
        )
        batch_op.create_index(
            "ix_sessions_conversation_cleanup",
            ["foundry_conversation_state", "foundry_conversation_next_cleanup_at"],
        )

    op.create_table(
        "session_turns",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("turn_key", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("frozen_step", sa.Integer(), nullable=False),
        sa.Column("frozen_context_revision", sa.Integer(), nullable=False),
        sa.Column("frozen_context_digest", sa.String(64), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_operation_id", sa.String(255), nullable=True),
        sa.Column("provider_response_id", sa.String(255), nullable=True),
        sa.Column("winning_attempt_id", sa.String(36), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("reconcile_after", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'leased', 'provider_pending', 'provider_unknown', "
            "'reconciling', 'succeeded', 'failed_terminal', 'cancelled')",
            name="ck_session_turn_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_session_turn_attempt_count_nonnegative"),
        sa.CheckConstraint("frozen_step >= 0", name="ck_session_turn_frozen_step_nonnegative"),
        sa.CheckConstraint(
            "frozen_context_revision >= 0", name="ck_session_turn_revision_nonnegative"
        ),
        sa.CheckConstraint(
            "winning_attempt_id IS NULL OR status = 'succeeded'",
            name="ck_session_turn_winner_requires_success",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["coaching_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn_key", name="uq_session_turn_key"),
        sa.UniqueConstraint("provider_response_id", name="uq_session_turn_provider_response_id"),
    )
    op.create_index("ix_session_turns_session_status", "session_turns", ["session_id", "status"])
    op.create_index("ix_session_turns_retry", "session_turns", ["status", "next_retry_at"])

    op.create_table(
        "session_turn_attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("provider_operation_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempt_number > 0", name="ck_session_turn_attempt_number_positive"),
        sa.ForeignKeyConstraint(["turn_id"], ["session_turns.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "attempt_number", name="uq_session_turn_attempt_number"),
    )
    with op.batch_alter_table("session_turns") as batch_op:
        batch_op.create_foreign_key(
            "fk_session_turns_winning_attempt",
            "session_turn_attempts",
            ["winning_attempt_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "session_turn_attempt_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("provider_response_id", sa.String(255), nullable=True),
        sa.Column("provider_call_id", sa.String(255), nullable=True),
        sa.Column("terminal_classification", sa.String(64), nullable=True),
        sa.Column("sanitized_error_digest", sa.String(64), nullable=True),
        sa.Column("event_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("observed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_kind IN ('dispatched', 'known_success', 'known_failure', 'timeout', "
            "'unknown', 'reconciled_success', 'reconciled_failure', 'winner_selected', "
            "'late_duplicate', 'cleanup_observed')",
            name="ck_session_turn_attempt_event_kind",
        ),
        sa.CheckConstraint(
            "event_sequence > 0", name="ck_session_turn_attempt_event_sequence_positive"
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["session_turn_attempts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id", "event_sequence", name="uq_session_turn_attempt_event_sequence"
        ),
    )

    op.create_table(
        "session_turn_context_audits",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("turn_key", sa.String(36), nullable=False),
        sa.Column("terminal_status", sa.String(32), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("agent_version", sa.String(50), nullable=False),
        sa.Column("skill_id", sa.String(36), nullable=False),
        sa.Column("skill_version_id", sa.String(36), nullable=False),
        sa.Column("sop_snapshot_digest", sa.String(64), nullable=False),
        sa.Column("focus_digest", sa.String(64), nullable=False),
        sa.Column("context_digest", sa.String(64), nullable=False),
        sa.Column("context_schema_version", sa.String(20), nullable=False),
        sa.Column("applied_step", sa.Integer(), nullable=False),
        sa.Column("applied_context_revision", sa.Integer(), nullable=False),
        sa.Column("user_message_id", sa.String(36), nullable=True),
        sa.Column("assistant_message_id", sa.String(36), nullable=True),
        sa.Column("conversation_digest", sa.String(64), nullable=False),
        sa.Column("winning_attempt_id", sa.String(36), nullable=True),
        sa.Column("provider_response_id", sa.String(255), nullable=True),
        sa.Column("iq_correlation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("progression_result", sa.String(32), nullable=False),
        sa.Column("progression_from_step", sa.Integer(), nullable=False),
        sa.Column("progression_to_step", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "terminal_status IN ('succeeded', 'failed_terminal', 'cancelled')",
            name="ck_session_turn_context_audit_terminal_status",
        ),
        sa.CheckConstraint("applied_step >= 0", name="ck_session_turn_audit_step_nonnegative"),
        sa.CheckConstraint(
            "applied_context_revision >= 0",
            name="ck_session_turn_audit_revision_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["session_messages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["coaching_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["turn_id"], ["session_turns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_message_id"], ["session_messages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["winning_attempt_id"], ["session_turn_attempts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn_key", name="uq_session_turn_context_audit"),
        sa.UniqueConstraint("turn_id", name="uq_session_turn_context_audit_turn"),
    )


def downgrade() -> None:
    """Remove Phase 31 tables and columns without touching pre-existing data."""
    op.drop_table("session_turn_context_audits")
    op.drop_table("session_turn_attempt_events")
    with op.batch_alter_table("session_turns") as batch_op:
        batch_op.drop_constraint("fk_session_turns_winning_attempt", type_="foreignkey")
    op.drop_table("session_turn_attempts")
    op.drop_index("ix_session_turns_retry", table_name="session_turns")
    op.drop_index("ix_session_turns_session_status", table_name="session_turns")
    op.drop_table("session_turns")

    with op.batch_alter_table("coaching_sessions") as batch_op:
        batch_op.drop_index("ix_sessions_conversation_cleanup")
        batch_op.drop_constraint("ck_sessions_context_revision_nonnegative", type_="check")
        batch_op.drop_constraint(
            "ck_sessions_conversation_cleanup_retries_nonnegative", type_="check"
        )
        batch_op.drop_constraint(
            "ck_sessions_conversation_create_retries_nonnegative", type_="check"
        )
        batch_op.drop_constraint("ck_sessions_foundry_conversation_state", type_="check")
        batch_op.drop_column("foundry_conversation_closed_at")
        batch_op.drop_column("foundry_conversation_cleanup_started_at")
        batch_op.drop_column("foundry_conversation_created_at")
        batch_op.drop_column("foundry_conversation_last_error")
        batch_op.drop_column("foundry_conversation_next_cleanup_at")
        batch_op.drop_column("foundry_conversation_cleanup_retry_count")
        batch_op.drop_column("foundry_conversation_create_retry_count")
        batch_op.drop_column("foundry_conversation_delete_lease_expires_at")
        batch_op.drop_column("foundry_conversation_delete_lease_token")
        batch_op.drop_column("foundry_conversation_create_lease_expires_at")
        batch_op.drop_column("foundry_conversation_create_lease_token")
        batch_op.drop_column("foundry_conversation_create_idempotency_id")
        batch_op.drop_column("foundry_conversation_create_operation_id")
        batch_op.drop_column("foundry_conversation_state")
        batch_op.drop_column("foundry_conversation_id")
        batch_op.drop_column("context_revision")
        batch_op.drop_column("sop_snapshot_sha256")
        batch_op.drop_column("sop_snapshot_json")
