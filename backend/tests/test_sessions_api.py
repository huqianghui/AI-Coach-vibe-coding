"""Tests for Sessions API endpoints: session lifecycle via HTTP."""

import json
from unittest.mock import patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.scoring_rubric import ScoringRubric
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.agent_chat_service import AgentResponseEvent
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _mock_agent_stream(*_args, **_kwargs):
    """Return a deterministic hosted-Agent stream for Session API tests."""
    yield AgentResponseEvent(kind="text", text="Mock HCP response")
    yield AgentResponseEvent(kind="completed", response_id="resp-session-api-test")


@pytest.fixture(autouse=True)
def mock_session_agent_stream():
    """Keep Session API unit tests independent of Azure credentials."""
    with patch("app.api.sessions.stream_agent_response", _mock_agent_stream):
        yield


async def _create_vl_instance(user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    async with TestSessionLocal() as session:
        inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
        session.add(inst)
        await session.commit()
        await session.refresh(inst)
        return inst.id


async def _create_admin_and_token() -> tuple[str, str]:
    """Create an admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_sess",
            email="admin_sess@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin Sessions",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_user_and_token(username="user_sess") -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Regular User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_active_scenario(client, admin_id, admin_token) -> str:
    """Create an HCP profile, rubric, and active scenario. Returns scenario_id."""
    vl_id = await _create_vl_instance(admin_id)
    hcp_resp = await client.post(
        "/api/v1/hcp-profiles",
        json={
            "name": "Dr. Sess",
            "specialty": "Onc",
            "created_by": admin_id,
            "voice_live_instance_id": vl_id,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    hcp_id = hcp_resp.json()["id"]

    # Session creation accepts only an authoritative hosted Prompt Agent.
    # Keep this fixture deterministic instead of depending on external Foundry sync.
    async with TestSessionLocal() as db:
        hcp = await db.get(HcpProfile, hcp_id)
        hcp.agent_id = "hcp-api-agent"
        hcp.agent_version = "21"
        hcp.agent_sync_status = "synced"
        await db.commit()

    # Create rubric and skill via DB
    async with TestSessionLocal() as db:
        rubric = ScoringRubric(
            name="Test Rubric",
            scenario_type="f2f",
            dimensions=json.dumps(
                [
                    {"name": "key_message", "weight": 30, "criteria": [], "max_score": 100.0},
                    {
                        "name": "objection_handling",
                        "weight": 25,
                        "criteria": [],
                        "max_score": 100.0,
                    },
                    {"name": "communication", "weight": 20, "criteria": [], "max_score": 100.0},
                    {"name": "product_knowledge", "weight": 15, "criteria": [], "max_score": 100.0},
                    {"name": "scientific_info", "weight": 10, "criteria": [], "max_score": 100.0},
                ]
            ),
            is_default=True,
            created_by=admin_id,
        )
        db.add(rubric)
        await db.flush()

        skill = Skill(
            id="test-skill-id", name="Test Skill", status="published", created_by=admin_id
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

    scn_resp = await client.post(
        "/api/v1/scenarios",
        json={
            "name": "Active Scenario",
            "tags": ["product:Brukinsa"],
            "hcp_profile_id": hcp_id,
            "rubric_id": rubric_id,
            "skill_id": "test-skill-id",
            "key_messages": ["Superior PFS", "Better safety"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    scenario_id = scn_resp.json()["id"]

    # Activate the scenario so sessions can be created
    async with TestSessionLocal() as db:
        from sqlalchemy import update

        from app.models.scenario import Scenario

        await db.execute(update(Scenario).where(Scenario.id == scenario_id).values(status="active"))
        await db.commit()

    return scenario_id


class TestCreateSessionEndpoint:
    """Tests for POST /api/v1/sessions/."""

    async def test_user_creates_session(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)

        user_id, user_token = await _create_user_and_token()
        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["scenario_id"] == scenario_id
        assert data["user_id"] == user_id
        assert data["agent_name"] == "hcp-api-agent"
        assert data["agent_version"] == "21"

    async def test_request_agent_fields_cannot_override_server_snapshot(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("pin_override_user")

        response = await client.post(
            "/api/v1/sessions",
            json={
                "scenario_id": scenario_id,
                "agent_name": "attacker-selected-agent",
                "agent_version": "999",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 201
        assert response.json()["agent_name"] == "hcp-api-agent"
        assert response.json()["agent_version"] == "21"

    async def test_unsynced_hcp_returns_structured_error(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("unsynced_agent_user")
        async with TestSessionLocal() as db:
            from app.models.scenario import Scenario

            scenario = await db.get(Scenario, scenario_id)
            hcp = await db.get(HcpProfile, scenario.hcp_profile_id)
            hcp.agent_sync_status = "failed"
            await db.commit()

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "HCP_AGENT_NOT_SYNCED"
        assert response.json()["details"] == {"sync_status": "failed"}

    async def test_no_auth_returns_401(self, client):
        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": "any"},
        )
        assert response.status_code == 401

    async def test_nonexistent_scenario_returns_404(self, client):
        _, user_token = await _create_user_and_token("user_sess_404")
        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": "nonexistent"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 404


class TestCreateSessionModeEndpoint:
    """Tests for POST /api/v1/sessions with mode parameter (Plan 08-06)."""

    async def test_create_session_with_voice_mode(self, client):
        """POST /sessions with mode=voice_pipeline stores mode on session response."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("voice_mode_user")

        with patch("app.api.sessions.settings") as mock_settings:
            mock_settings.feature_voice_live_enabled = True
            mock_settings.default_llm_provider = "mock"
            response = await client.post(
                "/api/v1/sessions",
                json={"scenario_id": scenario_id, "mode": "voice_pipeline"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "voice_pipeline"

    async def test_create_session_with_avatar_mode(self, client):
        """POST /sessions with mode=digital_human_pipeline stores mode on session response."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("avatar_mode_user")

        with patch("app.api.sessions.settings") as mock_settings:
            mock_settings.feature_voice_live_enabled = True
            mock_settings.default_llm_provider = "mock"
            response = await client.post(
                "/api/v1/sessions",
                json={"scenario_id": scenario_id, "mode": "digital_human_pipeline"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "digital_human_pipeline"

    async def test_create_session_default_mode_is_text(self, client):
        """POST /sessions without mode field defaults to text."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("default_mode_user")

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "text"

    async def test_create_session_invalid_mode_returns_422(self, client):
        """POST /sessions with invalid mode returns 422 (Literal type enforcement)."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("invalid_mode_user")

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id, "mode": "invalid_mode"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 422

    async def test_create_session_voice_mode_rejected_when_disabled(self, client):
        """POST /sessions with mode=voice_pipeline returns 409 when voice_live_enabled is false."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("voice_disabled_user")

        with patch("app.api.sessions.settings") as mock_settings:
            mock_settings.feature_voice_live_enabled = False
            response = await client.post(
                "/api/v1/sessions",
                json={"scenario_id": scenario_id, "mode": "voice_pipeline"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "VOICE_MODE_DISABLED"

    async def test_create_session_avatar_mode_rejected_when_disabled(self, client):
        """POST /sessions with mode=digital_human_pipeline returns 409 when disabled."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("avatar_disabled_user")

        with patch("app.api.sessions.settings") as mock_settings:
            mock_settings.feature_voice_live_enabled = False
            response = await client.post(
                "/api/v1/sessions",
                json={"scenario_id": scenario_id, "mode": "digital_human_pipeline"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "VOICE_MODE_DISABLED"

    async def test_create_session_text_mode_allowed_when_voice_disabled(self, client):
        """POST /sessions with mode=text succeeds even when voice_live_enabled is false."""
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("text_always_user")

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id, "mode": "text"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "text"


class TestListSessionsEndpoint:
    """Tests for GET /api/v1/sessions/."""

    async def test_lists_user_sessions(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        user_id, user_token = await _create_user_and_token()

        # Create two sessions and send messages so they are not filtered as abandoned
        resp1 = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        resp2 = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Add a message to each session so they won't be filtered out
        sid1 = resp1.json()["id"]
        sid2 = resp2.json()["id"]
        await client.post(
            f"/api/v1/sessions/{sid1}/transcript",
            json={"role": "user", "message": "Hello"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        await client.post(
            f"/api/v1/sessions/{sid2}/transcript",
            json={"role": "user", "message": "Hi"},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        response = await client.get(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2


class TestGetSessionEndpoint:
    """Tests for GET /api/v1/sessions/{session_id}."""

    async def test_get_own_session(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token()

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == session_id

    async def test_other_user_gets_403(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token()

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = create_resp.json()["id"]

        # Different user
        _, other_token = await _create_user_and_token("other_user_sess")
        response = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 403


class TestEndSessionEndpoint:
    """Tests for POST /api/v1/sessions/{session_id}/end."""

    async def test_end_in_progress_session(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token()

        # Create session
        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = create_resp.json()["id"]

        # Send a message to transition to in_progress
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello doctor"},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # End session
        response = await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    async def test_end_created_session_returns_200(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token()

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"


class TestGetSessionMessagesEndpoint:
    """Tests for GET /api/v1/sessions/{session_id}/messages."""

    async def test_get_messages_after_sending(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token()

        create_resp = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = create_resp.json()["id"]

        # Send a message (this triggers SSE response via mock adapter)
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Get messages - at minimum the user message should be saved
        response = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        # At least the user message should exist
        assert len(messages) >= 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
