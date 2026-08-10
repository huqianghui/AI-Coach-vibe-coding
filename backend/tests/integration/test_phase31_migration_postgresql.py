"""Real PostgreSQL roundtrip and concurrency proof for the Phase 31 migration."""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration
REVISION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic/versions/b35a_phase31_session_turn_outbox.py"
)


def _url() -> str:
    url = os.getenv("PHASE31_POSTGRES_URL")
    if not url:
        pytest.fail(
            "PHASE31_POSTGRES_URL is required and must target a disposable real PostgreSQL database"
        )
    if not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        pytest.fail("PHASE31_POSTGRES_URL must use PostgreSQL/psycopg2, not another engine")
    return url


def _migration_module():
    spec = importlib.util.spec_from_file_location("phase31_postgresql_migration", REVISION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection: sa.Connection, function) -> None:
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    function.__globals__["op"] = operations
    function()


def _previous_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()
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
    metadata.create_all(connection)


def _insert_turn(connection: sa.Connection, turn_id: str, key: str) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO session_turns "
            "(id, session_id, turn_key, status, input_digest, frozen_step, "
            "frozen_context_revision, frozen_context_digest, attempt_count) VALUES "
            "(:id, 'session-1', :key, 'pending', :digest, 0, 0, :digest, 0)"
        ),
        {"id": turn_id, "key": key, "digest": "a" * 64},
    )


def test_phase31_postgresql_upgrade_downgrade_constraints_and_transactions() -> None:
    engine = sa.create_engine(_url(), isolation_level="READ COMMITTED")
    schema = f"phase31_{uuid.uuid4().hex}"
    migration = _migration_module()
    try:
        with engine.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            _previous_schema(connection)
            connection.execute(
                sa.text("INSERT INTO coaching_sessions (id, name) VALUES ('session-1', 'existing')")
            )
            _run(connection, migration.upgrade)
            _insert_turn(connection, "turn-1", "key-1")
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
                    "UPDATE session_turns SET status='succeeded', winning_attempt_id='attempt-1', "
                    "provider_response_id='resp-1' WHERE id='turn-1'"
                )
            )

        with engine.connect() as connection:
            connection.execute(sa.text(f'SET search_path TO "{schema}"'))
            connection.commit()
            transaction = connection.begin()
            _insert_turn(connection, "turn-rollback", "rollback")
            transaction.rollback()
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM session_turns WHERE id='turn-rollback'")
                )
                == 0
            )
            connection.rollback()

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                _insert_turn(connection, "turn-duplicate", "key-1")

        with engine.begin() as connection:
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            _insert_turn(connection, "turn-null-provider-1", "null-provider-1")
            _insert_turn(connection, "turn-null-provider-2", "null-provider-2")

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                _insert_turn(connection, "turn-provider-duplicate", "provider-duplicate")
                connection.execute(
                    sa.text(
                        "UPDATE session_turns SET status='succeeded', "
                        "provider_response_id='resp-1' WHERE id='turn-provider-duplicate'"
                    )
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                connection.execute(sa.text("DELETE FROM coaching_sessions WHERE id='session-1'"))

        with engine.begin() as connection:
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            _insert_turn(connection, "turn-cas", "cas")

        with engine.begin() as first:
            first.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            won = first.execute(
                sa.text(
                    "UPDATE session_turns SET lease_owner='worker-a', status='leased' "
                    "WHERE id='turn-cas' AND status='pending'"
                )
            )
            assert won.rowcount == 1
        with engine.begin() as second:
            second.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            lost = second.execute(
                sa.text(
                    "UPDATE session_turns SET lease_owner='worker-b' "
                    "WHERE id='turn-cas' AND status='pending'"
                )
            )
            assert lost.rowcount == 0

        with engine.begin() as connection:
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            existing_name = connection.scalar(
                sa.text("SELECT name FROM coaching_sessions WHERE id='session-1'")
            )
            assert existing_name == "existing"
            _run(connection, migration.downgrade)
            assert not sa.inspect(connection).has_table("session_turns")
            preserved_name = connection.scalar(
                sa.text("SELECT name FROM coaching_sessions WHERE id='session-1'")
            )
            assert preserved_name == "existing"
            _run(connection, migration.upgrade)
            assert sa.inspect(connection).has_table("session_turn_context_audits")
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
