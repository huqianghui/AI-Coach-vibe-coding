"""Tests for the session service: session lifecycle, messaging, key message detection."""

import json
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select

from app.models.hcp_profile import HcpProfile
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.models.user import User
from app.services.auth import get_password_hash
from app.services.session_service import (
    _mock_key_message_detection,
    create_session,
    detect_key_messages,
    end_session,
    get_active_session,
    get_session,
    get_session_messages,
    get_user_sessions,
    resolve_pinned_agent,
    save_message,
)
from app.utils.exceptions import AppException, NotFoundException


async def _seed_user_and_scenario(db) -> tuple[str, str]:
    """Create a user with an active scenario. Returns (user_id, scenario_id)."""
    user = User(
        username="sessionuser",
        email="session@test.com",
        hashed_password=get_password_hash("pass"),
        full_name="Session User",
        role="user",
    )
    db.add(user)
    await db.flush()

    hcp = HcpProfile(
        name="Dr. Wang",
        specialty="Oncology",
        created_by=user.id,
        agent_id="hcp-session-agent",
        agent_version="7",
        agent_sync_status="synced",
    )
    db.add(hcp)
    await db.flush()

    scenario = Scenario(
        name="Active Scenario",
        hcp_profile_id=hcp.id,
        key_messages=json.dumps(["Superior PFS data", "Favorable safety profile"]),
        status="active",
        created_by=user.id,
        rubric_id="test-rubric-id",
        skill_id="test-skill-id",
    )
    db.add(scenario)
    await db.flush()

    return user.id, scenario.id


class TestCreateSession:
    """Tests for create_session."""

    async def test_creates_session_with_correct_status(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        assert session.status == "created"
        assert session.user_id == user_id
        assert session.scenario_id == scenario_id
        assert session.agent_name == "hcp-session-agent"
        assert session.agent_version == "7"
        assert session.agent_response_id is None

    async def test_existing_pin_is_immutable_and_new_session_uses_latest_profile(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        original = await create_session(db_session, scenario_id, user_id)

        scenario = await db_session.get(Scenario, scenario_id)
        hcp = await db_session.get(HcpProfile, scenario.hcp_profile_id)
        hcp.agent_id = "hcp-republished-agent"
        hcp.agent_version = "8"
        hcp.agent_sync_status = "synced"
        await db_session.flush()

        replacement = await create_session(db_session, scenario_id, user_id)
        resolved_original = await resolve_pinned_agent(original)

        assert (original.agent_name, original.agent_version) == ("hcp-session-agent", "7")
        assert (resolved_original.name, resolved_original.version) == ("hcp-session-agent", "7")
        assert (replacement.agent_name, replacement.agent_version) == (
            "hcp-republished-agent",
            "8",
        )

    async def test_missing_hcp_rejects_before_session_is_added(self):
        scenario = MagicMock(
            status="active",
            hcp_profile=None,
            key_messages="[]",
            skill_id=None,
            skill_version_id=None,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = scenario
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()

        with pytest.raises(AppException) as exc_info:
            await create_session(db, "scenario-without-hcp", "user-id")

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "HCP_AGENT_SOURCE_MISSING"
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    @pytest.mark.parametrize(
        ("updates", "expected_code"),
        [
            ({"agent_sync_status": "pending"}, "HCP_AGENT_NOT_SYNCED"),
            ({"agent_sync_status": "none"}, "HCP_AGENT_NOT_SYNCED"),
            ({"agent_sync_status": "failed"}, "HCP_AGENT_NOT_SYNCED"),
            ({"agent_id": ""}, "AGENT_PIN_MISSING"),
            ({"agent_id": "   "}, "AGENT_PIN_MISSING"),
            ({"agent_id": "asst_classic"}, "AGENT_PIN_INVALID"),
            ({"agent_version": ""}, "AGENT_PIN_MISSING"),
            ({"agent_version": "   "}, "AGENT_PIN_MISSING"),
        ],
    )
    async def test_invalid_agent_source_rejects_before_session_flush(
        self, db_session, updates, expected_code
    ):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        scenario = await db_session.get(Scenario, scenario_id)
        hcp = await db_session.get(HcpProfile, scenario.hcp_profile_id)
        for field, value in updates.items():
            setattr(hcp, field, value)
        await db_session.flush()
        before = await db_session.scalar(select(func.count()).select_from(CoachingSession))

        with pytest.raises(AppException) as exc_info:
            await create_session(db_session, scenario_id, user_id)

        after = await db_session.scalar(select(func.count()).select_from(CoachingSession))
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == expected_code
        assert after == before

    async def test_agent_pin_normalizes_only_surrounding_whitespace(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        scenario = await db_session.get(Scenario, scenario_id)
        hcp = await db_session.get(HcpProfile, scenario.hcp_profile_id)
        hcp.agent_id = "  hcp-exact-name  "
        hcp.agent_version = "  0042  "
        await db_session.flush()

        session = await create_session(db_session, scenario_id, user_id)

        assert session.agent_name == "hcp-exact-name"
        assert session.agent_version == "0042"

    async def test_initializes_key_messages_status(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        km_status = json.loads(session.key_messages_status)
        assert len(km_status) == 2
        assert all(not item["delivered"] for item in km_status)
        assert all(item["detected_at"] is None for item in km_status)

    async def test_raises_for_nonexistent_scenario(self, db_session):
        user_id, _ = await _seed_user_and_scenario(db_session)
        with pytest.raises(NotFoundException):
            await create_session(db_session, "nonexistent-id", user_id)

    async def test_raises_for_inactive_scenario(self, db_session):
        user_id, _ = await _seed_user_and_scenario(db_session)

        # Create a draft scenario
        hcp = HcpProfile(name="Dr. X", specialty="Derm", created_by=user_id)
        db_session.add(hcp)
        await db_session.flush()

        draft = Scenario(
            name="Draft",
            hcp_profile_id=hcp.id,
            key_messages="[]",
            status="draft",
            created_by=user_id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
        )
        db_session.add(draft)
        await db_session.flush()

        with pytest.raises(AppException) as exc_info:
            await create_session(db_session, draft.id, user_id)
        assert exc_info.value.code == "SCENARIO_NOT_ACTIVE"


class TestGetSession:
    """Tests for get_session (ownership check)."""

    async def test_returns_session_for_owner(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        created = await create_session(db_session, scenario_id, user_id)

        result = await get_session(db_session, created.id, user_id)
        assert result.id == created.id

    async def test_raises_for_wrong_user(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        created = await create_session(db_session, scenario_id, user_id)

        with pytest.raises(AppException) as exc_info:
            await get_session(db_session, created.id, "other-user-id")
        assert exc_info.value.status_code == 403

    async def test_raises_for_nonexistent_session(self, db_session):
        with pytest.raises(NotFoundException):
            await get_session(db_session, "nonexistent", "user")


class TestResolvePinnedAgent:
    """Tests for the fail-closed, session-only Agent pin resolver."""

    async def test_returns_immutable_reference_for_valid_pin(self):
        session = CoachingSession(agent_name="hcp-pinned", agent_version="12")

        reference = await resolve_pinned_agent(session)

        assert reference.name == "hcp-pinned"
        assert reference.version == "12"
        with pytest.raises(FrozenInstanceError):
            reference.version = "13"

    @pytest.mark.parametrize("field", ["agent_name", "agent_version"])
    @pytest.mark.parametrize("value", [None, "", "   "])
    async def test_rejects_missing_or_blank_pin_fields(self, field, value):
        session = CoachingSession(agent_name="hcp-pinned", agent_version="12")
        setattr(session, field, value)

        with pytest.raises(AppException) as exc_info:
            await resolve_pinned_agent(session)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "AGENT_PIN_MISSING"
        assert exc_info.value.details == {"field": field}

    async def test_rejects_classic_assistant_identity(self):
        session = CoachingSession(agent_name="  asst_legacy  ", agent_version="12")

        with pytest.raises(AppException) as exc_info:
            await resolve_pinned_agent(session)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "AGENT_PIN_INVALID"

    async def test_resolves_original_pin_without_hcp_relationship_or_lookup(self):
        session = CoachingSession(agent_name="hcp-original", agent_version="3")
        session.scenario = None

        reference = await resolve_pinned_agent(session)

        assert reference.name == "hcp-original"
        assert reference.version == "3"


class TestGetUserSessions:
    """Tests for get_user_sessions (pagination)."""

    async def test_returns_empty_for_no_sessions(self, db_session):
        sessions, total = await get_user_sessions(db_session, "no-user")
        assert sessions == []
        assert total == 0

    async def test_returns_sessions_with_total(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session1 = await create_session(db_session, scenario_id, user_id)
        session2 = await create_session(db_session, scenario_id, user_id)
        await save_message(db_session, session1.id, "user", "hello")
        await save_message(db_session, session2.id, "user", "hello again")

        sessions, total = await get_user_sessions(db_session, user_id)
        assert total == 2
        assert len(sessions) == 2

    async def test_pagination_limits_results(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        for _ in range(5):
            session = await create_session(db_session, scenario_id, user_id)
            await save_message(db_session, session.id, "user", "hello")

        sessions, total = await get_user_sessions(db_session, user_id, page=1, page_size=2)
        assert total == 5
        assert len(sessions) == 2


class TestGetActiveSession:
    """Tests for get_active_session."""

    async def test_returns_none_when_no_active(self, db_session):
        result = await get_active_session(db_session, "no-user")
        assert result is None

    async def test_returns_in_progress_session(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)
        # Transition to in_progress by saving first user message
        await save_message(db_session, session.id, "user", "Hello")

        active = await get_active_session(db_session, user_id)
        assert active is not None
        assert active.status == "in_progress"


class TestSaveMessage:
    """Tests for save_message."""

    async def test_saves_message_with_correct_index(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        msg = await save_message(db_session, session.id, "user", "Hello doctor")
        assert msg.message_index == 0
        assert msg.role == "user"
        assert msg.content == "Hello doctor"

    async def test_increments_message_index(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        await save_message(db_session, session.id, "user", "First")
        msg2 = await save_message(db_session, session.id, "assistant", "Second")
        assert msg2.message_index == 1

    async def test_first_user_message_transitions_to_in_progress(self, db_session):
        from sqlalchemy import select

        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        await save_message(db_session, session.id, "user", "Hello")

        result = await db_session.execute(
            select(CoachingSession).where(CoachingSession.id == session.id)
        )
        updated = result.scalar_one()
        assert updated.status == "in_progress"
        assert updated.started_at is not None
        assert updated.started_at.tzinfo is None

    async def test_assistant_message_does_not_transition(self, db_session):
        from sqlalchemy import select

        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        await save_message(db_session, session.id, "assistant", "Welcome")

        result = await db_session.execute(
            select(CoachingSession).where(CoachingSession.id == session.id)
        )
        updated = result.scalar_one()
        assert updated.status == "created"


class TestEndSession:
    """Tests for end_session."""

    async def test_ends_in_progress_session(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)
        await save_message(db_session, session.id, "user", "Hello")

        ended = await end_session(db_session, session.id, user_id)
        assert ended.status == "completed"
        assert ended.completed_at is not None
        assert ended.completed_at.tzinfo is None
        assert ended.started_at is not None
        assert ended.started_at.tzinfo is None
        assert ended.duration_seconds is not None

    async def test_raises_for_wrong_user(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)
        await save_message(db_session, session.id, "user", "Hello")

        with pytest.raises(AppException) as exc_info:
            await end_session(db_session, session.id, "other-user")
        assert exc_info.value.status_code == 403

    async def test_allows_created_status(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)

        ended = await end_session(db_session, session.id, user_id)

        assert ended.status == "completed"
        assert ended.duration_seconds == 0

    async def test_raises_for_nonexistent_session(self, db_session):
        with pytest.raises(NotFoundException):
            await end_session(db_session, "nonexistent", "user")


class TestGetSessionMessages:
    """Tests for get_session_messages."""

    async def test_returns_ordered_messages(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)
        await save_message(db_session, session.id, "user", "First")
        await save_message(db_session, session.id, "assistant", "Second")

        messages = await get_session_messages(db_session, session.id)
        assert len(messages) == 2
        assert messages[0].message_index == 0
        assert messages[1].message_index == 1


class TestMockKeyMessageDetection:
    """Tests for the pure _mock_key_message_detection function."""

    async def test_detects_message_with_keyword_overlap(self):
        key_msgs = ["Superior PFS data compared to ibrutinib"]
        mr_message = "Brukinsa shows superior PFS data in clinical trials compared to alternatives"
        detected = _mock_key_message_detection(key_msgs, mr_message, [])
        assert len(detected) == 1

    async def test_does_not_detect_unrelated_message(self):
        key_msgs = ["Superior PFS data compared to ibrutinib"]
        mr_message = "Hello doctor, nice to meet you"
        detected = _mock_key_message_detection(key_msgs, mr_message, [])
        assert len(detected) == 0

    async def test_ignores_short_words(self):
        # Words <= 3 chars are skipped
        key_msgs = ["PFS is ok in the trial"]
        # "PFS" is only 3 chars, "the" is 3, "ok" is 2, "is" is 2
        # Significant words: "trial" (5 chars)
        mr_message = "The trial was good"
        detected = _mock_key_message_detection(key_msgs, mr_message, [])
        assert "PFS is ok in the trial" in detected

    async def test_skips_key_messages_with_no_significant_words(self):
        key_msgs = ["is a go"]
        # All words <= 3 chars
        mr_message = "is a go"
        detected = _mock_key_message_detection(key_msgs, mr_message, [])
        assert len(detected) == 0

    async def test_case_insensitive_matching(self):
        key_msgs = ["Superior Efficacy Data"]
        mr_message = "we have superior efficacy data from ALPINE trial"
        detected = _mock_key_message_detection(key_msgs, mr_message, [])
        assert len(detected) == 1


class TestDetectKeyMessages:
    """DB integration tests for detect_key_messages."""

    async def test_updates_key_messages_status(self, db_session):
        user_id, scenario_id = await _seed_user_and_scenario(db_session)
        session = await create_session(db_session, scenario_id, user_id)
        await save_message(db_session, session.id, "user", "Superior PFS data is remarkable")

        # Reload session to have fresh key_messages_status
        from sqlalchemy import select

        result = await db_session.execute(
            select(CoachingSession).where(CoachingSession.id == session.id)
        )
        session = result.scalar_one()

        updated_status = await detect_key_messages(
            db_session, session, "Superior PFS data is remarkable"
        )

        # Should detect "Superior PFS data" if keyword match works
        delivered = [km for km in updated_status if km["delivered"]]
        assert len(delivered) >= 1
