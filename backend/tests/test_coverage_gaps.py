"""Targeted tests to bring every file to >=95% coverage.

Covers specific uncovered lines in:
- sessions.py: SSE streaming, active session, messages, report, suggestions
- scoring.py: get_score_history, trigger_scoring, get_session_score
- auth.py: login token creation path
- hcp_profiles.py: CRUD endpoint bodies
- scenarios.py: CRUD + clone endpoint bodies
- scoring_rubric.py: weight validation edge cases
- dependencies.py: inactive user check
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.scoring_rubric import ScoringRubric
from app.models.session import CoachingSession
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.services.agent_chat_service import AgentResponseEvent
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal

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


async def _mock_agent_stream(*_args, **_kwargs):
    """Return a deterministic hosted-Agent stream for API coverage tests."""
    yield AgentResponseEvent(kind="text", text="Mock HCP response")
    yield AgentResponseEvent(kind="completed", response_id="resp-coverage-test")


@pytest.fixture(autouse=True)
def mock_session_agent_stream():
    """Keep Session API unit tests independent of Azure credentials."""
    with patch("app.api.sessions.stream_agent_response", _mock_agent_stream):
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

# ────────────────── helpers ──────────────────


async def _user(role="user", username="covuser") -> tuple[str, str]:
    """Create a user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as db:
        u = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Coverage User",
            role=role,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        token = create_access_token(data={"sub": u.id})
        return u.id, token


async def _create_vl_instance(user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    from app.models.voice_live_instance import VoiceLiveInstance

    async with TestSessionLocal() as db:
        inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
        db.add(inst)
        await db.commit()
        await db.refresh(inst)
        return inst.id


async def _inactive_user(username="inactive") -> tuple[str, str]:
    """Create an inactive user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as db:
        u = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Inactive User",
            role="user",
            is_active=False,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        token = create_access_token(data={"sub": u.id})
        return u.id, token


async def _admin_scenario(client, admin_id, admin_token) -> str:
    """Create an HCP profile + rubric + skill + active scenario. Returns scenario_id."""
    vl_id = await _create_vl_instance(admin_id)
    hcp = await client.post(
        "/api/v1/hcp-profiles",
        json={
            "name": "Dr. Cov",
            "specialty": "Onc",
            "created_by": admin_id,
            "voice_live_instance_id": vl_id,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    hcp_id = hcp.json()["id"]
    async with TestSessionLocal() as db:
        profile = await db.get(HcpProfile, hcp_id)
        profile.agent_id = "dr-cov-agent"
        profile.agent_version = "1"
        profile.agent_sync_status = "synced"
        await db.commit()
    # Create rubric + skill via DB (no API endpoint needed)
    async with TestSessionLocal() as db:
        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=_DEFAULT_RUBRIC_DIMS,
            is_default=True,
            created_by=admin_id,
        )
        db.add(rubric)
        await db.flush()

        skill = Skill(
            id="test-skill-id",
            name="Test Skill",
            status="published",
            created_by=admin_id,
        )
        db.add(skill)
        await db.flush()

        skill_ver = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content="test",
            is_published=True,
            created_by=admin_id,
        )
        db.add(skill_ver)
        await db.commit()
        await db.refresh(rubric)
        rubric_id = rubric.id

    scn = await client.post(
        "/api/v1/scenarios",
        json={
            "name": "Cov Scenario",
            "tags": ["product:Brukinsa"],
            "hcp_profile_id": hcp_id,
            "rubric_id": rubric_id,
            "skill_id": "test-skill-id",
            "key_messages": ["Superior PFS", "Better safety"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    scenario_id = scn.json()["id"]

    # Activate the scenario so sessions can be created against it
    async with TestSessionLocal() as db:
        from sqlalchemy import update

        await db.execute(update(Scenario).where(Scenario.id == scenario_id).values(status="active"))
        await db.commit()

    return scenario_id


async def _completed_session_with_messages() -> tuple[str, str, str]:
    """Seed a completed session with messages, return (user_id, session_id, token)."""
    async with TestSessionLocal() as db:
        user = User(
            username="comp_user",
            email="comp@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Comp",
            role="user",
        )
        db.add(user)
        await db.flush()

        hcp = HcpProfile(name="Dr. Comp", specialty="Onc", created_by=user.id)
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
            name="Comp Scenario",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["PFS", "Safety"]),
            skill_id="test-skill-id",
            status="active",
            created_by=user.id,
            rubric_id=rubric.id,
        )
        db.add(scenario)
        await db.flush()

        session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status="completed",
            key_messages_status=json.dumps(
                [
                    {"message": "PFS", "delivered": True, "detected_at": None},
                    {"message": "Safety", "delivered": False, "detected_at": None},
                ]
            ),
        )
        db.add(session)
        await db.flush()

        msg = SessionMessage(
            session_id=session.id, role="user", content="PFS data", message_index=0
        )
        db.add(msg)
        await db.commit()

        token = create_access_token(data={"sub": user.id})
        return user.id, session.id, token


# ────────────────── dependencies.py: inactive user (lines 33-38) ──────────────────


class TestInactiveUserDependency:
    """Cover dependencies.py lines 33-38: inactive user rejection."""

    async def test_inactive_user_gets_401(self, client):
        _, token = await _inactive_user("inactive_dep")
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "INACTIVE_USER"


# ────────────────── auth.py: login endpoint body (lines 18-19) ──────────────────


class TestAuthLoginBody:
    """Cover auth.py lines 18-19: successful login creates access_token."""

    async def test_login_returns_valid_jwt_token(self, client):
        await _user(role="admin", username="login_body")
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "login_body", "password": "pass"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify the token works
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "login_body"

    async def test_auth_refresh_returns_new_token(self, client):
        _, token = await _user(role="user", username="refresh_user")
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()


# ────────────────── scoring.py: all 3 endpoints (lines 23, 39-40, 55-58) ──────────────────


class TestScoringApiCoverage:
    """Cover scoring.py: get_score_history, trigger_scoring, get_session_score."""

    async def test_get_score_history_endpoint(self, client):
        """Cover line 23: return await scoring_service.get_score_history(...)."""
        _, token = await _user(role="user", username="hist_user")
        response = await client.get(
            "/api/v1/scoring/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        # Empty history is valid
        assert isinstance(response.json(), list)

    async def test_get_score_history_with_limit(self, client):
        _, token = await _user(role="user", username="hist_limit")
        response = await client.get(
            "/api/v1/scoring/history?limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    async def test_trigger_scoring_endpoint(self, client):
        """Cover lines 39-40: score_session and return score."""
        user_id, session_id, token = await _completed_session_with_messages()
        response = await client.post(
            f"/api/v1/scoring/sessions/{session_id}/score",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "overall_score" in data
        assert "details" in data

    async def test_get_session_score_endpoint(self, client):
        """Cover lines 55-58: get score or raise 404."""
        user_id, session_id, token = await _completed_session_with_messages()

        # Score it first
        await client.post(
            f"/api/v1/scoring/sessions/{session_id}/score",
            headers={"Authorization": f"Bearer {token}"},
        )

        response = await client.get(
            f"/api/v1/scoring/sessions/{session_id}/score",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id

    async def test_get_session_score_not_scored_404(self, client):
        """Cover lines 56-57: score is None raises NotFoundException."""
        _, session_id, token = await _completed_session_with_messages()
        response = await client.get(
            f"/api/v1/scoring/sessions/{session_id}/score",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


# ────────────────── sessions.py: full endpoint coverage ──────────────────


class TestSessionsApiCoverage:
    """Cover sessions.py: create, list, active, get, message, end, report."""

    async def test_create_session_returns_201(self, client):
        """Cover line 42."""
        admin_id, admin_token = await _user(role="admin", username="sa_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        uid, utoken = await _user(role="user", username="sa_user")

        resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

    async def test_list_sessions_paginated(self, client):
        """Cover line 54. Sessions with messages appear; abandoned (no messages) are filtered."""
        admin_id, admin_token = await _user(role="admin", username="sl_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="sl_user")

        # Create a session and send a message so it won't be filtered as abandoned
        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        # Persist a transcript message so the session has at least one message
        await client.post(
            f"/api/v1/sessions/{session_id}/transcript",
            json={"role": "user", "message": "Hello doctor"},
            headers={"Authorization": f"Bearer {utoken}"},
        )

        resp = await client.get(
            "/api/v1/sessions?page=1&page_size=10",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_get_active_session_no_active(self, client):
        """Cover lines 65-71: no active session raises 404."""
        _, utoken = await _user(role="user", username="noactive_user")
        resp = await client.get(
            "/api/v1/sessions/active",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_ACTIVE_SESSION"

    async def test_get_active_session_found(self, client):
        """Cover lines 64-71: active session returned."""
        admin_id, admin_token = await _user(role="admin", username="act_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="act_user")

        # Create and transition to in_progress via message
        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {utoken}"},
        )

        resp = await client.get(
            "/api/v1/sessions/active",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == session_id

    async def test_get_session_by_id(self, client):
        """Cover line 82."""
        admin_id, admin_token = await _user(role="admin", username="gs_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="gs_user")

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == session_id

    async def test_send_message_sse_stream(self, client):
        """Cover lines 95-186: SSE event_generator including text, key_messages, hints, done."""
        admin_id, admin_token = await _user(role="admin", username="sse_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="sse_user")

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        # Send message — this triggers SSE streaming
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Tell me about Superior PFS data and Better safety profile"},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        # SSE returns 200 with text/event-stream
        assert resp.status_code == 200
        body = resp.text
        # SSE stream should contain event types
        assert "event:" in body or "data:" in body

    async def test_send_message_to_closed_session_409(self, client):
        """Cover lines 95-100: SESSION_CLOSED for completed session."""
        admin_id, admin_token = await _user(role="admin", username="closed_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="closed_user")

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        # Send a message to transition to in_progress
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {utoken}"},
        )

        # End the session
        await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {utoken}"},
        )

        # Try to send another message
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Still here?"},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 409

    async def test_end_session_endpoint(self, client):
        """Cover line 199."""
        admin_id, admin_token = await _user(role="admin", username="end_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="end_user")

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        # Transition to in_progress
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Start"},
            headers={"Authorization": f"Bearer {utoken}"},
        )

        resp = await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    async def test_get_session_messages_endpoint(self, client):
        """Cover lines 214-215."""
        admin_id, admin_token = await _user(role="admin", username="msg_admin")
        scenario_id = await _admin_scenario(client, admin_id, admin_token)
        _, utoken = await _user(role="user", username="msg_user")

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {utoken}"},
        )
        session_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Test message"},
            headers={"Authorization": f"Bearer {utoken}"},
        )

        resp = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        msgs = resp.json()
        assert isinstance(msgs, list)
        assert len(msgs) >= 1

    async def test_get_session_report_endpoint(self, client):
        """Cover lines 227-228."""
        user_id, session_id, token = await _completed_session_with_messages()

        # Score the session first
        await client.post(
            f"/api/v1/scoring/sessions/{session_id}/score",
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = await client.get(
            f"/api/v1/sessions/{session_id}/report",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "overall_score" in resp.json()

    async def test_get_session_suggestions_endpoint(self, client):
        """Cover lines 239-247."""
        async with TestSessionLocal() as db:
            user = User(
                username="sug_user2",
                email="sug2@test.com",
                hashed_password=get_password_hash("pass"),
                full_name="Sug User",
                role="user",
            )
            db.add(user)
            await db.flush()

            hcp = HcpProfile(name="Dr. Sug2", specialty="Onc", created_by=user.id)
            db.add(hcp)
            await db.flush()

            rubric = ScoringRubric(
                name="Sug Rubric",
                scenario_type="f2f",
                dimensions=_DEFAULT_RUBRIC_DIMS,
                is_default=True,
                created_by=user.id,
            )
            db.add(rubric)
            await db.flush()

            scenario = Scenario(
                name="Sug Scenario",
                hcp_profile_id=hcp.id,
                key_messages=json.dumps(["PFS", "Safety"]),
                skill_id="sug-test-skill-id",
                status="active",
                created_by=user.id,
                rubric_id=rubric.id,
            )
            db.add(scenario)
            await db.flush()

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
            db.add(session)
            await db.flush()

            msgs = [
                SessionMessage(
                    session_id=session.id, role="user", content="PFS data", message_index=0
                ),
                SessionMessage(
                    session_id=session.id, role="assistant", content="Tell me more", message_index=1
                ),
            ]
            db.add_all(msgs)
            await db.commit()

            token = create_access_token(data={"sub": user.id})
            sid = session.id

        resp = await client.get(
            f"/api/v1/sessions/{sid}/suggestions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ────────────────── hcp_profiles.py: CRUD bodies (lines 50,58,69,101,113,124) ──────────────────


class TestHcpProfilesCoverage:
    """Cover hcp_profiles.py lines: create body, datetime_to_str, list, get, update, delete."""

    async def test_create_hcp_profile(self, client):
        """Cover line 69: create_hcp_profile + return."""
        admin_id, admin_token = await _user(role="admin", username="hcp_admin")
        vl_id = await _create_vl_instance(admin_id)
        resp = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Cover",
                "specialty": "Cardiology",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Dr. Cover"
        # Verify datetime_to_str ran (lines 50, 58)
        assert "created_at" in data
        assert "updated_at" in data

    async def test_list_hcp_profiles_with_search(self, client):
        """Cover list endpoint with search param."""
        admin_id, admin_token = await _user(role="admin", username="hcp_list_admin")
        vl_id = await _create_vl_instance(admin_id)
        await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Searchable",
                "specialty": "Oncology",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await client.get(
            "/api/v1/hcp-profiles?search=Searchable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_get_hcp_profile_by_id(self, client):
        """Cover line 101."""
        admin_id, admin_token = await _user(role="admin", username="hcp_get_admin")
        vl_id = await _create_vl_instance(admin_id)
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. GetTest",
                "specialty": "Derm",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = create_resp.json()["id"]
        resp = await client.get(
            f"/api/v1/hcp-profiles/{pid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    async def test_update_hcp_profile(self, client):
        """Cover line 113."""
        admin_id, admin_token = await _user(role="admin", username="hcp_upd_admin")
        vl_id = await _create_vl_instance(admin_id)
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Before",
                "specialty": "Neuro",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = create_resp.json()["id"]
        resp = await client.put(
            f"/api/v1/hcp-profiles/{pid}",
            json={"name": "Dr. After"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Dr. After"

    async def test_delete_hcp_profile(self, client):
        """Cover line 124."""
        admin_id, admin_token = await _user(role="admin", username="hcp_del_admin")
        vl_id = await _create_vl_instance(admin_id)
        create_resp = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. Delete",
                "specialty": "Onc",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pid = create_resp.json()["id"]
        resp = await client.delete(
            f"/api/v1/hcp-profiles/{pid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204


# ────────────────── scenarios.py: CRUD bodies (lines 50,58,69,113,125,136,147) ──────────────────


class TestScenariosCoverage:
    """Cover scenarios.py: create, list, get, update, delete, clone, active."""

    async def _create_hcp(self, client, admin_token, admin_id) -> str:
        vl_id = await _create_vl_instance(admin_id)
        resp = await client.post(
            "/api/v1/hcp-profiles",
            json={
                "name": "Dr. ScnCov",
                "specialty": "Onc",
                "created_by": admin_id,
                "voice_live_instance_id": vl_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        return resp.json()["id"]

    async def _seed_skill(self, admin_id: str, skill_id: str = "scn-cov-skill"):
        """Seed a skill + version for scenario creation."""
        async with TestSessionLocal() as db:
            skill = Skill(id=skill_id, name="Cov Skill", status="published", created_by=admin_id)
            db.add(skill)
            await db.flush()
            skill_ver = SkillVersion(
                skill_id=skill.id,
                version_number=1,
                content="test",
                is_published=True,
                created_by=admin_id,
            )
            db.add(skill_ver)
            await db.commit()
        return skill_id

    async def test_create_scenario(self, client):
        """Cover line 69."""
        admin_id, admin_token = await _user(role="admin", username="scn_cr_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-cr-skill")
        resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Cov Scenario",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["Msg1"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Cov Scenario"
        assert "created_at" in data

    async def test_list_scenarios_with_filter(self, client):
        admin_id, admin_token = await _user(role="admin", username="scn_ls_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-ls-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Active Scn",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Activate the scenario
        sid = create_resp.json()["id"]
        async with TestSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(update(Scenario).where(Scenario.id == sid).values(status="active"))
            await db.commit()

        resp = await client.get(
            "/api/v1/scenarios?status=active",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_list_active_scenarios_user(self, client):
        """Cover scenarios.py /active endpoint."""
        admin_id, admin_token = await _user(role="admin", username="scn_act_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-act-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "User Active Scn",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Activate the scenario
        sid = create_resp.json()["id"]
        async with TestSessionLocal() as db:
            from sqlalchemy import update

            await db.execute(update(Scenario).where(Scenario.id == sid).values(status="active"))
            await db.commit()

        _, utoken = await _user(role="user", username="scn_act_user")
        resp = await client.get(
            "/api/v1/scenarios/active",
            headers={"Authorization": f"Bearer {utoken}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_scenario_by_id(self, client):
        """Cover line 113."""
        admin_id, admin_token = await _user(role="admin", username="scn_get_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-get-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Get Scn",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        sid = create_resp.json()["id"]
        resp = await client.get(
            f"/api/v1/scenarios/{sid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == sid

    async def test_update_scenario(self, client):
        """Cover line 125."""
        admin_id, admin_token = await _user(role="admin", username="scn_upd_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-upd-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Before",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        sid = create_resp.json()["id"]
        resp = await client.put(
            f"/api/v1/scenarios/{sid}",
            json={"name": "After"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    async def test_delete_scenario(self, client):
        """Cover line 136."""
        admin_id, admin_token = await _user(role="admin", username="scn_del_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-del-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Delete Scn",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        sid = create_resp.json()["id"]
        resp = await client.delete(
            f"/api/v1/scenarios/{sid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    async def test_clone_scenario(self, client):
        """Cover line 147."""
        admin_id, admin_token = await _user(role="admin", username="scn_cln_admin")
        hcp_id = await self._create_hcp(client, admin_token, admin_id)
        skill_id = await self._seed_skill(admin_id, "scn-cln-skill")
        create_resp = await client.post(
            "/api/v1/scenarios",
            json={
                "name": "Clone Src",
                "tags": ["product:Drug"],
                "hcp_profile_id": hcp_id,
                "rubric_id": "test-rubric-id",
                "skill_id": skill_id,
                "key_messages": ["M"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        sid = create_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/scenarios/{sid}/clone",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"].startswith("Clone Src")


# ── scoring_rubric.py: weight validation (lines 33-34, 58-59, 85) ──


class TestScoringRubricValidation:
    """Cover scoring_rubric.py: weight validation in RubricCreate and RubricUpdate."""

    def test_rubric_create_weights_must_sum_100(self):
        """Cover lines 33-34: weights don't sum to 100."""
        from app.schemas.scoring_rubric import RubricCreate

        with pytest.raises(Exception) as exc_info:
            RubricCreate(
                name="Bad Rubric",
                dimensions=[
                    {"name": "Dim1", "weight": 60, "criteria": ["c1"]},
                    {"name": "Dim2", "weight": 30, "criteria": ["c2"]},
                ],
            )
        assert "100" in str(exc_info.value)

    def test_rubric_create_weights_sum_100_ok(self):
        """Valid rubric."""
        from app.schemas.scoring_rubric import RubricCreate

        rubric = RubricCreate(
            name="Good Rubric",
            dimensions=[
                {"name": "Dim1", "weight": 60, "criteria": ["c1"]},
                {"name": "Dim2", "weight": 40, "criteria": ["c2"]},
            ],
        )
        assert rubric.name == "Good Rubric"

    def test_rubric_update_weights_must_sum_100(self):
        """Cover lines 58-59: update weights validation."""
        from app.schemas.scoring_rubric import RubricUpdate

        with pytest.raises(Exception) as exc_info:
            RubricUpdate(
                dimensions=[
                    {"name": "Dim1", "weight": 50, "criteria": ["c1"]},
                    {"name": "Dim2", "weight": 30, "criteria": ["c2"]},
                ],
            )
        assert "100" in str(exc_info.value)

    def test_rubric_update_none_dimensions_ok(self):
        """Cover line 55: dimensions=None bypasses validation."""
        from app.schemas.scoring_rubric import RubricUpdate

        rubric = RubricUpdate(name="Updated Name")
        assert rubric.dimensions is None

    def test_rubric_response_parses_json_dimensions(self):
        """Cover line 85: parse_dimensions_json with JSON string input."""
        from app.schemas.scoring_rubric import RubricResponse

        resp = RubricResponse(
            id="test-id",
            name="Test",
            description="Test rubric",
            scenario_type="f2f",
            dimensions='[{"name":"Dim1","weight":100,"criteria":["c1"],"max_score":100.0}]',
            is_default=False,
            created_by="user-1",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert isinstance(resp.dimensions, list)
        assert resp.dimensions[0].name == "Dim1"

    def test_rubric_response_list_dimensions_passthrough(self):
        """Cover line 85: parse_dimensions_json with list input."""
        from app.schemas.scoring_rubric import RubricResponse

        resp = RubricResponse(
            id="test-id2",
            name="Test2",
            description="Test rubric 2",
            scenario_type="f2f",
            dimensions=[{"name": "Dim1", "weight": 100, "criteria": ["c1"], "max_score": 100.0}],
            is_default=True,
            created_by="user-2",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert resp.dimensions[0].name == "Dim1"
