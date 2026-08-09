"""SQLite roundtrip proof for the Phase 31 Session turn outbox migration."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

REVISION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic/versions/b35a_phase31_session_turn_outbox.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("phase31_migration", REVISION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _previous_schema(metadata: sa.MetaData) -> None:
    sa.Table(
        "coaching_sessions",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False, server_default="user-1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
    )
    sa.Table(
        "session_messages",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
    )


def _run(connection: sa.Connection, function) -> None:
    context = MigrationContext.configure(
        connection,
        opts={"render_as_batch": True, "target_metadata": sa.MetaData()},
    )
    operations = Operations(context)
    function.__globals__["op"] = operations
    function()


def test_phase31_sqlite_upgrade_downgrade_preserves_data_and_constraints(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'phase31.sqlite'}")

    @sa.event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    metadata = sa.MetaData()
    _previous_schema(metadata)
    metadata.create_all(engine)
    migration = _migration_module()
    assert migration.revision == "b35a_phase31_turn_outbox"
    assert migration.down_revision == "a34a_session_agent_pin"

    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO coaching_sessions (id, name) VALUES ('session-1', 'existing')")
        )
        _run(connection, migration.upgrade)
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("coaching_sessions")
        }
        assert {"sop_snapshot_json", "foundry_conversation_id", "context_revision"} <= columns
        assert (
            connection.scalar(sa.text("SELECT name FROM coaching_sessions WHERE id = 'session-1'"))
            == "existing"
        )
        connection.execute(
            sa.text(
                "INSERT INTO session_turns "
                "(id, session_id, turn_key, status, input_digest, frozen_step, "
                "frozen_context_revision, frozen_context_digest, attempt_count) VALUES "
                "('turn-1', 'session-1', 'key-1', 'pending', :digest, 0, 0, :digest, 0)"
            ),
            {"digest": "a" * 64},
        )
        connection.execute(
            sa.text(
                "INSERT INTO session_turn_attempts "
                "(id, turn_id, attempt_number, request_digest, lease_token, correlation_id) "
                "VALUES ('attempt-1', 'turn-1', 1, :digest, 'lease', 'correlation')"
            ),
            {"digest": "b" * 64},
        )
        connection.execute(
            sa.text(
                "INSERT INTO session_turn_attempt_events "
                "(id, attempt_id, event_sequence, event_kind) "
                "VALUES ('event-1', 'attempt-1', 1, 'winner_selected')"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE session_turns SET status='succeeded', "
                "winning_attempt_id='attempt-1', provider_response_id='resp-1' "
                "WHERE id='turn-1'"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO session_turn_context_audits "
                "(id, session_id, turn_id, turn_key, terminal_status, agent_name, "
                "agent_version, skill_id, skill_version_id, sop_snapshot_digest, focus_digest, "
                "context_digest, context_schema_version, applied_step, "
                "applied_context_revision, conversation_digest, winning_attempt_id, "
                "progression_result, progression_from_step, progression_to_step) VALUES "
                "('audit-1', 'session-1', 'turn-1', 'key-1', 'succeeded', 'agent', '1', "
                "'skill', 'version', :digest, :digest, :digest, '1', 0, 0, :digest, "
                "'attempt-1', 'advanced', 0, 1)"
            ),
            {"digest": "c" * 64},
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM session_turn_attempt_events")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM session_turn_context_audits")) == 1

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO session_turns "
                    "(id, session_id, turn_key, status, input_digest, frozen_step, "
                    "frozen_context_revision, frozen_context_digest, attempt_count) VALUES "
                    "('turn-2', 'session-1', 'key-1', 'pending', :digest, 0, 0, :digest, 0)"
                ),
                {"digest": "b" * 64},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM coaching_sessions WHERE id='session-1'"))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO session_turn_attempts "
                    "(id, turn_id, attempt_number, request_digest, lease_token, correlation_id) "
                    "VALUES ('attempt-2', 'turn-1', 1, :digest, 'lease', 'correlation')"
                ),
                {"digest": "d" * 64},
            )

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        transaction = connection.begin()
        _run(connection, migration.downgrade)
        assert not sa.inspect(connection).has_table("session_turns")
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("coaching_sessions")
        }
        assert "sop_snapshot_json" not in columns
        assert (
            connection.scalar(sa.text("SELECT name FROM coaching_sessions WHERE id = 'session-1'"))
            == "existing"
        )
        _run(connection, migration.upgrade)
        assert sa.inspect(connection).has_table("session_turn_context_audits")
        transaction.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()

    engine.dispose()
