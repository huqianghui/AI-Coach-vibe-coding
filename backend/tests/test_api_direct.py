"""Direct API function call tests to ensure coverage tracking works.

Bypasses ASGI transport to guarantee coverage tracks async function execution.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.scoring_rubric import ScoringRubric
from app.models.session import CoachingSession
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.schemas.auth import LoginRequest
from app.services.auth import create_access_token, get_password_hash
from app.utils.exceptions import AppException
from tests.conftest import TestSessionLocal


async def _create_vl_instance(db, user_id: str) -> str:
    """Create a minimal VoiceLiveInstance and return its id.

    D-13: HcpProfileCreate requires voice_live_instance_id -- tests that go
    through the create_profile() API function need a real VoiceLiveInstance
    row to link.
    """
    inst = VoiceLiveInstance(name="Direct Test VL Instance", created_by=user_id)
    db.add(inst)
    await db.flush()
    return inst.id


_MOCK_LLM_RESULT = {
    "overall_score": 75.0,
    "passed": True,
    "feedback_summary": "Good performance overall.",
    "dimensions": [
        {
            "dimension": "key_message",
            "score": 80,
            "weight": 30,
            "category": "content",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        },
        {
            "dimension": "objection_handling",
            "score": 70,
            "weight": 25,
            "category": "content",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        },
        {
            "dimension": "communication",
            "score": 75,
            "weight": 20,
            "category": "content",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        },
        {
            "dimension": "product_knowledge",
            "score": 72,
            "weight": 15,
            "category": "content",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        },
        {
            "dimension": "scientific_info",
            "score": 68,
            "weight": 10,
            "category": "content",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        },
    ],
}


@pytest.fixture(autouse=True)
def mock_llm_scoring():
    """Mock LLM scoring for all tests (no Azure OpenAI in test env)."""
    with patch(
        "app.services.scoring_service.score_with_llm",
        new_callable=AsyncMock,
        return_value=_MOCK_LLM_RESULT,
    ):
        yield


_DEFAULT_RUBRIC_DIMS = json.dumps(
    [
        {"name": "key_message", "weight": 30, "criteria": [], "max_score": 100.0},
        {"name": "objection_handling", "weight": 25, "criteria": [], "max_score": 100.0},
        {"name": "communication", "weight": 20, "criteria": [], "max_score": 100.0},
        {"name": "product_knowledge", "weight": 15, "criteria": [], "max_score": 100.0},
        {"name": "scientific_info", "weight": 10, "criteria": [], "max_score": 100.0},
    ]
)

# ────────── auth.py direct calls ──────────


class TestAuthDirect:
    """Direct calls to auth endpoint functions."""

    async def test_login_function_directly(self, db_session):
        """Cover auth.py lines 18-19 via direct function call."""
        from app.api.auth import login

        user = User(
            username="direct_login",
            email="direct@test.com",
            hashed_password=get_password_hash("pass123"),
            full_name="Direct",
            role="user",
        )
        db_session.add(user)
        await db_session.commit()

        request = LoginRequest(username="direct_login", password="pass123")
        result = await login(request=request, db=db_session)
        assert result.access_token is not None
        assert result.token_type == "bearer"

    async def test_refresh_function_directly(self):
        """Cover auth.py line 31-32."""
        from app.api.auth import refresh_token

        async with TestSessionLocal() as db:
            user = User(
                username="direct_refresh",
                email="drefresh@test.com",
                hashed_password=get_password_hash("pass"),
                full_name="Refresh",
                role="user",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        result = await refresh_token(current_user=user)
        assert result.access_token is not None

    async def test_get_me_directly(self):
        """Cover auth.py line 25."""
        from app.api.auth import get_me

        async with TestSessionLocal() as db:
            user = User(
                username="direct_me",
                email="dme@test.com",
                hashed_password=get_password_hash("pass"),
                full_name="Me",
                role="user",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        result = await get_me(current_user=user)
        assert result.username == "direct_me"


# ────────── scoring.py direct calls ──────────


class TestScoringDirect:
    """Direct calls to scoring endpoint functions."""

    async def _seed_completed_session(self, db):
        user = User(
            username="dscore",
            email="dscore@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DScore",
            role="user",
        )
        db.add(user)
        await db.flush()

        hcp = HcpProfile(name="Dr. DScore", specialty="Onc", created_by=user.id)
        db.add(hcp)
        await db.flush()

        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=_DEFAULT_RUBRIC_DIMS,
            is_default=True,
            created_by=user.id,
        )
        db.add(rubric)
        await db.flush()

        scenario = Scenario(
            name="DScore Scn",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["PFS"]),
            skill_id="test-skill-id",
            status="active",
            rubric_id=rubric.id,
            created_by=user.id,
        )
        db.add(scenario)
        await db.flush()

        session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status="completed",
            key_messages_status=json.dumps(
                [{"message": "PFS", "delivered": True, "detected_at": None}]
            ),
        )
        db.add(session)
        await db.flush()

        msg = SessionMessage(
            session_id=session.id, role="user", content="PFS data", message_index=0
        )
        db.add(msg)
        await db.commit()
        return user, session

    async def test_get_score_history_directly(self, db_session):
        """Cover scoring.py line 23."""
        from app.api.scoring import get_score_history

        user = User(
            username="dhist",
            email="dhist@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DHist",
            role="user",
        )
        db_session.add(user)
        await db_session.commit()

        result = await get_score_history(limit=10, db=db_session, user=user)
        assert isinstance(result, list)

    async def test_trigger_scoring_directly(self, db_session):
        """Cover scoring.py lines 39-40."""
        from app.api.scoring import trigger_scoring

        user, session = await self._seed_completed_session(db_session)
        result = await trigger_scoring(session_id=session.id, db=db_session, user=user)
        assert result is not None

    async def test_get_session_score_directly(self, db_session):
        """Cover scoring.py lines 55-58."""
        from app.api.scoring import get_session_score, trigger_scoring

        user, session = await self._seed_completed_session(db_session)
        await trigger_scoring(session_id=session.id, db=db_session, user=user)
        await db_session.commit()

        result = await get_session_score(session_id=session.id, db=db_session, user=user)
        assert result is not None


# ────────── sessions.py direct calls ──────────


class TestSessionsDirect:
    """Direct calls to session endpoint functions."""

    async def _seed_scenario(self, db):
        user = User(
            username="dsess",
            email="dsess@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DSess",
            role="user",
        )
        db.add(user)
        await db.flush()

        hcp = HcpProfile(
            name="Dr. DSess",
            specialty="Onc",
            created_by=user.id,
            agent_id="dr-dsess-agent",
            agent_version="1",
            agent_sync_status="synced",
        )
        db.add(hcp)
        await db.flush()

        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=_DEFAULT_RUBRIC_DIMS,
            is_default=True,
            created_by=user.id,
        )
        db.add(rubric)
        await db.flush()

        scenario = Scenario(
            name="DSess Scn",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["PFS", "Safety"]),
            skill_id="test-skill-id",
            status="active",
            rubric_id=rubric.id,
            created_by=user.id,
        )
        db.add(scenario)
        await db.flush()
        await db.commit()
        return user, scenario

    async def test_create_session_directly(self, db_session):
        """Cover sessions.py line 42."""
        from app.api.sessions import create_session
        from app.schemas.session import SessionCreate

        user, scenario = await self._seed_scenario(db_session)
        request = SessionCreate(scenario_id=scenario.id)
        result = await create_session(request=request, db=db_session, user=user)
        assert result.status == "created"

    async def test_list_sessions_directly(self, db_session):
        """Cover sessions.py line 54."""
        from app.api.sessions import list_sessions

        user, _scenario = await self._seed_scenario(db_session)
        result = await list_sessions(page=1, page_size=10, db=db_session, user=user)
        assert result.total >= 0

    async def test_get_active_session_no_active_directly(self, db_session):
        """Cover sessions.py lines 65-70 (no active session path)."""
        from app.api.sessions import get_active_session

        user, _ = await self._seed_scenario(db_session)
        with pytest.raises(AppException) as exc:
            await get_active_session(db=db_session, user=user)
        assert exc.value.status_code == 404

    async def test_get_active_session_with_active_directly(self, db_session):
        """Cover sessions.py line 71 (return active session)."""
        from app.api.sessions import get_active_session
        from app.services.session_service import create_session, save_message

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        # Transition to in_progress by sending first user message
        await save_message(db_session, session.id, "user", "Hello")
        await db_session.commit()

        result = await get_active_session(db=db_session, user=user)
        assert result.id == session.id
        assert result.status == "in_progress"

    async def test_send_message_closed_session_directly(self, db_session):
        """Cover sessions.py lines 95-100 (reject closed session)."""
        from app.api.sessions import send_message
        from app.schemas.session import SendMessageRequest
        from app.services.session_service import create_session, end_session, save_message

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        await save_message(db_session, session.id, "user", "Hello")
        session = await end_session(db_session, session.id, user.id)
        await db_session.commit()

        request = SendMessageRequest(message="Another message")
        with pytest.raises(AppException) as exc:
            await send_message(session_id=session.id, request=request, db=db_session, user=user)
        assert exc.value.code == "SESSION_CLOSED"

    async def test_send_message_sse_generator_directly(self, db_session):
        """Cover sessions.py lines 105-188 (SSE event_generator inner function).

        Captures the async generator before EventSourceResponse wraps it,
        then iterates it to cover all lines inside event_generator().
        """
        from app.services.agent_chat_service import AgentResponseEvent
        from app.services.session_service import create_session, save_message

        async def stream_agent(*_args, **_kwargs):
            yield AgentResponseEvent(kind="text", text="Hello doctor")
            yield AgentResponseEvent(kind="completed", response_id="resp-direct")

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        await save_message(db_session, session.id, "user", "Hello doctor")
        await db_session.commit()

        # Capture the generator before EventSourceResponse wraps it
        captured_gen = None

        class CapturingSSE:
            def __init__(self, content, *args, **kwargs):
                nonlocal captured_gen
                captured_gen = content

        import app.api.sessions as sessions_module

        original_sse = sessions_module.EventSourceResponse
        sessions_module.EventSourceResponse = CapturingSSE

        try:
            from app.schemas.session import SendMessageRequest

            request = SendMessageRequest(message="Hello doctor, I want to discuss PFS data")
            with patch("app.api.sessions.stream_agent_response", stream_agent):
                await sessions_module.send_message(
                    session_id=session.id, request=request, db=db_session, user=user
                )
                # Consume while the lazy SSE generator still sees the stream mock.
                assert captured_gen is not None
                events = []
                async for event in captured_gen:
                    events.append(event)

            # Verify we got expected event types
            event_types = [e["event"] for e in events]
            assert "text" in event_types
            assert "done" in event_types
            assert "key_messages" in event_types
        finally:
            sessions_module.EventSourceResponse = original_sse

    async def test_send_message_sse_with_suggestion_event(self, db_session):
        """Cover sessions.py line 145 (SUGGESTION event yield).

        Forces the mock adapter to always emit a SUGGESTION event by
        patching random to guarantee the 30% branch is taken.
        """
        from app.services.agent_chat_service import AgentResponseEvent
        from app.services.session_service import create_session, save_message

        async def stream_agent(*_args, **_kwargs):
            yield AgentResponseEvent(kind="text", text="PFS and safety")
            yield AgentResponseEvent(kind="completed", response_id="resp-suggestion")

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        await save_message(db_session, session.id, "user", "Hi")
        await db_session.commit()

        captured_gen = None

        class CapturingSSE:
            def __init__(self, content, *args, **kwargs):
                nonlocal captured_gen
                captured_gen = content

        import app.api.sessions as sessions_module

        original_sse = sessions_module.EventSourceResponse
        sessions_module.EventSourceResponse = CapturingSSE

        try:
            from app.schemas.session import SendMessageRequest

            request = SendMessageRequest(message="Tell me about the PFS Safety data please")
            suggestion = MagicMock()
            suggestion.message = "Mention the trial endpoint"
            suggestion.type.value = "key_message"
            suggestion.trigger = "missing"
            suggestion.relevance_score = 0.9
            with (
                patch("app.api.sessions.stream_agent_response", stream_agent),
                patch(
                    "app.api.sessions.generate_suggestions",
                    new=AsyncMock(return_value=[suggestion]),
                ),
            ):
                await sessions_module.send_message(
                    session_id=session.id, request=request, db=db_session, user=user
                )
                assert captured_gen is not None
                events = []
                async for event in captured_gen:
                    events.append(event)

            event_types = [e["event"] for e in events]
            # Must have "hint" from the SUGGESTION event (line 145)
            assert "hint" in event_types
        finally:
            sessions_module.EventSourceResponse = original_sse

    async def test_get_session_directly(self, db_session):
        """Cover sessions.py line 82."""
        from app.api.sessions import create_session, get_session
        from app.schemas.session import SessionCreate

        user, scenario = await self._seed_scenario(db_session)
        request = SessionCreate(scenario_id=scenario.id)
        created = await create_session(request=request, db=db_session, user=user)
        await db_session.commit()

        result = await get_session(session_id=created.id, db=db_session, user=user)
        assert result.id == created.id

    async def test_end_session_directly(self, db_session):
        """Cover sessions.py line 199."""
        from app.api.sessions import end_session
        from app.services.session_service import create_session, save_message

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        await save_message(db_session, session.id, "user", "Hello")
        await db_session.commit()

        result = await end_session(session_id=session.id, db=db_session, user=user)
        assert result.status == "completed"

    async def test_get_messages_directly(self, db_session):
        """Cover sessions.py lines 214-215."""
        from app.api.sessions import get_session_messages
        from app.services.session_service import create_session, save_message

        user, scenario = await self._seed_scenario(db_session)
        session = await create_session(db_session, scenario.id, user.id)
        await save_message(db_session, session.id, "user", "Test msg")
        await db_session.commit()

        result = await get_session_messages(session_id=session.id, db=db_session, user=user)
        assert len(result) >= 1

    async def test_get_report_directly(self, db_session):
        """Cover sessions.py lines 227-228."""
        from app.api.sessions import get_session_report
        from app.services.scoring_service import score_session

        user = User(
            username="drpt",
            email="drpt@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DReport",
            role="user",
        )
        db_session.add(user)
        await db_session.flush()

        hcp = HcpProfile(name="Dr. Rpt", specialty="Onc", created_by=user.id)
        db_session.add(hcp)
        await db_session.flush()

        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=_DEFAULT_RUBRIC_DIMS,
            is_default=True,
            created_by=user.id,
        )
        db_session.add(rubric)
        await db_session.flush()

        scenario = Scenario(
            name="Rpt Scn",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["PFS"]),
            skill_id="test-skill-id",
            status="active",
            rubric_id=rubric.id,
            created_by=user.id,
        )
        db_session.add(scenario)
        await db_session.flush()

        session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status="completed",
            key_messages_status=json.dumps(
                [{"message": "PFS", "delivered": True, "detected_at": None}]
            ),
        )
        db_session.add(session)
        await db_session.flush()

        msg = SessionMessage(
            session_id=session.id, role="user", content="PFS data", message_index=0
        )
        db_session.add(msg)
        await db_session.commit()

        await score_session(db_session, session.id)
        await db_session.commit()

        result = await get_session_report(session_id=session.id, db=db_session, user=user)
        assert result.session_id == session.id

    async def test_get_suggestions_directly(self, db_session):
        """Cover sessions.py lines 239-247."""
        from app.api.sessions import get_session_suggestions

        user = User(
            username="dsug",
            email="dsug@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DSug",
            role="user",
        )
        db_session.add(user)
        await db_session.flush()

        hcp = HcpProfile(name="Dr. Sug", specialty="Onc", created_by=user.id)
        db_session.add(hcp)
        await db_session.flush()

        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=_DEFAULT_RUBRIC_DIMS,
            is_default=True,
            created_by=user.id,
        )
        db_session.add(rubric)
        await db_session.flush()

        scenario = Scenario(
            name="Sug Scn",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["PFS", "Safety"]),
            skill_id="test-skill-id",
            status="active",
            rubric_id=rubric.id,
            created_by=user.id,
        )
        db_session.add(scenario)
        await db_session.flush()

        session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status="in_progress",
            key_messages_status=json.dumps(
                [
                    {"message": "PFS", "delivered": True, "detected_at": None},
                    {"message": "Safety", "delivered": False, "detected_at": None},
                ]
            ),
        )
        db_session.add(session)
        await db_session.flush()

        msgs = [
            SessionMessage(session_id=session.id, role="user", content="PFS data", message_index=0),
            SessionMessage(
                session_id=session.id, role="assistant", content="Tell me more", message_index=1
            ),
        ]
        db_session.add_all(msgs)
        await db_session.commit()

        result = await get_session_suggestions(session_id=session.id, db=db_session, user=user)
        assert isinstance(result, list)


# ────────── hcp_profiles.py direct calls ──────────


class TestHcpProfilesDirect:
    """Direct calls to hcp_profiles endpoint functions."""

    async def test_create_profile_directly(self, db_session):
        """Cover hcp_profiles.py line 69."""
        from app.api.hcp_profiles import create_profile
        from app.schemas.hcp_profile import HcpProfileCreate

        user = User(
            username="dhcp_admin",
            email="dhcp@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DHCP",
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        vl_id = await _create_vl_instance(db_session, user.id)
        data = HcpProfileCreate(
            name="Dr. Direct", specialty="Onc", created_by=user.id, voice_live_instance_id=vl_id
        )
        result = await create_profile(data=data, db=db_session, user=user)
        assert result.name == "Dr. Direct"

    async def test_get_profile_directly(self, db_session):
        """Cover hcp_profiles.py line 101."""
        from app.api.hcp_profiles import create_profile, get_profile
        from app.schemas.hcp_profile import HcpProfileCreate

        user = User(
            username="dhcp_get",
            email="dhcp_get@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DGet",
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        vl_id = await _create_vl_instance(db_session, user.id)
        data = HcpProfileCreate(
            name="Dr. GetD", specialty="Onc", created_by=user.id, voice_live_instance_id=vl_id
        )
        created = await create_profile(data=data, db=db_session, user=user)
        await db_session.commit()

        result = await get_profile(profile_id=created.id, db=db_session, user=user)
        assert result.id == created.id

    async def test_update_profile_directly(self, db_session):
        """Cover hcp_profiles.py line 113."""
        from app.api.hcp_profiles import create_profile, update_profile
        from app.schemas.hcp_profile import HcpProfileCreate, HcpProfileUpdate

        user = User(
            username="dhcp_upd",
            email="dhcp_upd@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DUpd",
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        vl_id = await _create_vl_instance(db_session, user.id)
        data = HcpProfileCreate(
            name="Dr. Before", specialty="Onc", created_by=user.id, voice_live_instance_id=vl_id
        )
        created = await create_profile(data=data, db=db_session, user=user)
        await db_session.commit()

        upd = HcpProfileUpdate(name="Dr. After")
        result = await update_profile(profile_id=created.id, data=upd, db=db_session, user=user)
        assert result.name == "Dr. After"

    async def test_delete_profile_directly(self, db_session):
        """Cover hcp_profiles.py line 124."""
        from app.api.hcp_profiles import create_profile, delete_profile
        from app.schemas.hcp_profile import HcpProfileCreate

        user = User(
            username="dhcp_del",
            email="dhcp_del@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DDel",
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        vl_id = await _create_vl_instance(db_session, user.id)
        data = HcpProfileCreate(
            name="Dr. Del", specialty="Onc", created_by=user.id, voice_live_instance_id=vl_id
        )
        created = await create_profile(data=data, db=db_session, user=user)
        await db_session.commit()

        result = await delete_profile(profile_id=created.id, db=db_session, user=user)
        assert result.status_code == 204


# ────────── scenarios.py direct calls ──────────


class TestScenariosDirect:
    """Direct calls to scenario endpoint functions."""

    async def _seed_hcp(self, db):
        user = User(
            username="dscn",
            email="dscn@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="DScn",
            role="admin",
        )
        db.add(user)
        await db.flush()

        hcp = HcpProfile(name="Dr. DScn", specialty="Onc", created_by=user.id)
        db.add(hcp)
        await db.flush()

        skill = Skill(
            id="test-skill-id",
            name="Test Skill",
            status="published",
            created_by=user.id,
        )
        db.add(skill)
        await db.flush()

        skill_version = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content="test content",
            is_published=True,
            created_by=user.id,
        )
        db.add(skill_version)
        await db.flush()
        await db.commit()
        return user, hcp

    async def test_create_scenario_directly(self, db_session):
        """Cover scenarios.py line 69."""
        from app.api.scenarios import create_scenario
        from app.schemas.scenario import ScenarioCreate

        user, hcp = await self._seed_hcp(db_session)
        data = ScenarioCreate(
            name="Direct Scn",
            hcp_profile_id=hcp.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
            key_messages=["M1"],
        )
        result = await create_scenario(data=data, db=db_session, user=user)
        assert result.name == "Direct Scn"

    async def test_get_scenario_directly(self, db_session):
        """Cover scenarios.py line 113."""
        from app.api.scenarios import create_scenario, get_scenario
        from app.schemas.scenario import ScenarioCreate

        user, hcp = await self._seed_hcp(db_session)
        data = ScenarioCreate(
            name="Get Scn",
            hcp_profile_id=hcp.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
            key_messages=["M1"],
        )
        created = await create_scenario(data=data, db=db_session, user=user)
        await db_session.commit()

        result = await get_scenario(scenario_id=created.id, db=db_session, user=user)
        assert result.id == created.id

    async def test_update_scenario_directly(self, db_session):
        """Cover scenarios.py line 125."""
        from app.api.scenarios import create_scenario, update_scenario
        from app.schemas.scenario import ScenarioCreate, ScenarioUpdate

        user, hcp = await self._seed_hcp(db_session)
        data = ScenarioCreate(
            name="Before Scn",
            hcp_profile_id=hcp.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
            key_messages=["M1"],
        )
        created = await create_scenario(data=data, db=db_session, user=user)
        await db_session.commit()

        upd = ScenarioUpdate(name="After Scn")
        result = await update_scenario(scenario_id=created.id, data=upd, db=db_session, user=user)
        assert result.name == "After Scn"

    async def test_delete_scenario_directly(self, db_session):
        """Cover scenarios.py line 136."""
        from app.api.scenarios import create_scenario, delete_scenario
        from app.schemas.scenario import ScenarioCreate

        user, hcp = await self._seed_hcp(db_session)
        data = ScenarioCreate(
            name="Del Scn",
            hcp_profile_id=hcp.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
            key_messages=["M1"],
        )
        created = await create_scenario(data=data, db=db_session, user=user)
        await db_session.commit()

        result = await delete_scenario(scenario_id=created.id, db=db_session, user=user)
        assert result.status_code == 204

    async def test_clone_scenario_directly(self, db_session):
        """Cover scenarios.py line 147."""
        from app.api.scenarios import clone_scenario, create_scenario
        from app.schemas.scenario import ScenarioCreate

        user, hcp = await self._seed_hcp(db_session)
        data = ScenarioCreate(
            name="Clone Src",
            hcp_profile_id=hcp.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
            key_messages=["M1"],
        )
        created = await create_scenario(data=data, db=db_session, user=user)
        await db_session.commit()

        result = await clone_scenario(scenario_id=created.id, db=db_session, user=user)
        assert "Clone Src" in result.name


# ────────── dependencies.py direct call ──────────


class TestDependenciesDirect:
    """Direct calls to dependency functions."""

    async def test_inactive_user_rejected(self, db_session):
        """Cover dependencies.py lines 36-37: inactive user check."""
        from app.dependencies import get_current_user

        user = User(
            username="dinactive",
            email="dinactive@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Inactive",
            role="user",
            is_active=False,
        )
        db_session.add(user)
        await db_session.commit()

        token = create_access_token(data={"sub": user.id})
        with pytest.raises(AppException) as exc:
            await get_current_user(token=token, db=db_session)
        assert exc.value.code == "INACTIVE_USER"

    async def test_invalid_token_rejected(self, db_session):
        """Cover dependencies.py lines 30-31: JWTError handling."""
        from app.dependencies import get_current_user

        with pytest.raises(AppException) as exc:
            await get_current_user(token="invalid.token.here", db=db_session)
        assert exc.value.code == "INVALID_TOKEN"

    async def test_missing_sub_rejected(self, db_session):
        """Cover dependencies.py lines 28-29: missing sub claim."""
        from jose import jwt

        from app.config import get_settings
        from app.dependencies import get_current_user

        settings = get_settings()
        token = jwt.encode({}, settings.secret_key, algorithm=settings.algorithm)
        with pytest.raises(AppException) as exc:
            await get_current_user(token=token, db=db_session)
        assert exc.value.code == "INVALID_TOKEN"

    async def test_nonexistent_user_rejected(self, db_session):
        """Cover dependencies.py lines 34-35: user not found."""
        from app.dependencies import get_current_user

        token = create_access_token(data={"sub": "nonexistent-user-id"})
        with pytest.raises(AppException) as exc:
            await get_current_user(token=token, db=db_session)
        assert exc.value.code == "USER_NOT_FOUND"
