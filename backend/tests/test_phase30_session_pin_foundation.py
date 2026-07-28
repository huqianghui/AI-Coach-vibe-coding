"""Foundation tests for immutable Phase 30 session Agent pins."""

from datetime import UTC, datetime
from importlib import util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import CoachingSession
from app.schemas.session import SessionCreate, SessionResponse

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION_FILE = "a34a_add_session_agent_pin.py"
PHASE_30_COLUMNS = {"agent_name", "agent_version", "agent_response_id"}


def _load_migration() -> ModuleType:
    spec = util.spec_from_file_location(
        "a34a_add_session_agent_pin_test",
        MIGRATIONS_DIR / MIGRATION_FILE,
    )
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session_response_data(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    data: dict[str, object] = {
        "id": "session-1",
        "user_id": "user-1",
        "scenario_id": "scenario-1",
        "status": "created",
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "key_messages_status": "[]",
        "overall_score": None,
        "passed": None,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return data


def test_migration_adds_exact_nullable_pin_columns_and_is_reversible(tmp_path: Path) -> None:
    """The migration must add only nullable pin fields and remove only those fields."""
    migration = _load_migration()
    assert migration.revision == "a34a_session_agent_pin"
    assert migration.down_revision == "z33a_drop_hcp_voice_fields"

    database_path = tmp_path / "session-pin.db"
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.schema.CreateTable(
                sa.Table(
                    "coaching_sessions",
                    sa.MetaData(),
                    sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("status", sa.String(20), nullable=False),
                )
            )
        )
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)

        existing_columns = sa.inspect(connection).get_columns("coaching_sessions")
        before = {column["name"] for column in existing_columns}
        migration.upgrade()
        upgraded_columns = {
            column["name"]: column
            for column in sa.inspect(connection).get_columns("coaching_sessions")
        }

        assert set(upgraded_columns) - before == PHASE_30_COLUMNS
        expected_lengths = {
            "agent_name": 100,
            "agent_version": 50,
            "agent_response_id": 255,
        }
        for name, length in expected_lengths.items():
            column = upgraded_columns[name]
            assert column["nullable"] is True
            assert column["default"] is None
            assert isinstance(column["type"], sa.String)
            assert column["type"].length == length

        migration.downgrade()
        downgraded = {
            column["name"] for column in sa.inspect(connection).get_columns("coaching_sessions")
        }
        assert downgraded == before

    engine.dispose()


@pytest.mark.asyncio
async def test_legacy_style_session_allows_null_agent_pin(db_session: AsyncSession) -> None:
    """Existing sessions remain valid without inventing historical Agent identity."""
    session = CoachingSession(user_id="legacy-user", scenario_id="legacy-scenario")

    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)

    assert session.agent_name is None
    assert session.agent_version is None
    assert session.agent_response_id is None


@pytest.mark.asyncio
async def test_session_agent_pin_round_trip(db_session: AsyncSession) -> None:
    """The ORM preserves distinct Agent identity and continuation values."""
    session = CoachingSession(
        user_id="user-1",
        scenario_id="scenario-1",
        agent_name="hcp-agent-name",
        agent_version="17",
        agent_response_id="resp_abc123",
    )
    db_session.add(session)
    await db_session.flush()
    session_id = session.id
    db_session.expunge(session)

    stored = await db_session.scalar(
        select(CoachingSession).where(CoachingSession.id == session_id)
    )

    assert stored is not None
    assert stored.agent_name == "hcp-agent-name"
    assert stored.agent_version == "17"
    assert stored.agent_response_id == "resp_abc123"


def test_session_response_exposes_nullable_audit_pins() -> None:
    """Session output includes nullable server-owned Agent audit identity."""
    response = SessionResponse.model_validate(
        _session_response_data(agent_name=None, agent_version=None)
    )

    assert response.model_dump()["agent_name"] is None
    assert response.model_dump()["agent_version"] is None

    pinned = SessionResponse.model_validate(
        _session_response_data(agent_name="hcp-agent", agent_version="42")
    )
    assert pinned.agent_name == "hcp-agent"
    assert pinned.agent_version == "42"


def test_session_response_never_exposes_internal_continuation_id() -> None:
    """Responses must not disclose the internal Responses API continuation ID."""
    response = SessionResponse.model_validate(
        _session_response_data(
            agent_name="hcp-agent",
            agent_version="42",
            agent_response_id="resp_secret",
        )
    )

    assert "agent_response_id" not in SessionResponse.model_fields
    assert "agent_response_id" not in response.model_dump()


def test_session_create_contract_has_no_agent_identity_fields() -> None:
    """Browser-owned session input cannot select Agent identity or continuation state."""
    assert set(SessionCreate.model_fields) == {"scenario_id", "mode"}

    request = SessionCreate.model_validate(
        {
            "scenario_id": "scenario-1",
            "agent_name": "attacker-agent",
            "agent_version": "999",
            "agent_response_id": "resp_attacker",
        }
    )
    assert request.model_dump() == {"scenario_id": "scenario-1", "mode": "text"}
