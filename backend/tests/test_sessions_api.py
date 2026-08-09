"""Tests for Sessions API endpoints: session lifecycle via HTTP."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.hcp_profile import HcpProfile
from app.models.scoring_rubric import ScoringRubric
from app.models.session_turn import SessionTurn
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.models.voice_live_instance import VoiceLiveInstance
from app.services import session_service
from app.services.auth import create_access_token, get_password_hash
from app.services.session_turn_orchestrator import TurnResult
from app.utils.exceptions import AppException
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def mock_session_agent_stream():
    """Keep Session API tests independent of external Foundry credentials."""

    async def build_orchestrator(_db):
        async def run_turn(session_id, turn_key, user_text, _worker_id):
            async with TestSessionLocal() as turn_db:
                await session_service.save_message(turn_db, session_id, "user", user_text)
                await session_service.save_message(
                    turn_db, session_id, "assistant", "Mock HCP response"
                )
                await turn_db.commit()
            return TurnResult(
                status="succeeded",
                turn_key=turn_key,
                text="Mock HCP response",
                response_id="resp-session-api-test",
            )

        return SimpleNamespace(run_turn=AsyncMock(side_effect=run_turn))

    with patch("app.api.sessions._session_turn_orchestrator", side_effect=build_orchestrator):
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

        skill_content = "# SOP\n## Step 1: Open\n## Step 2: Discover\n## Step 3: Close"
        skill = Skill(
            id="test-skill-id",
            name="Test Skill",
            content=skill_content,
            status="published",
            created_by=admin_id,
        )
        db.add(skill)
        await db.flush()
        skill_ver = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content=skill_content,
            metadata_json='{"knowledge_references":["test-reference"]}',
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

    async def test_request_agent_fields_are_rejected(self, client):
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

        assert response.status_code == 422

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
        assert [(message["role"], message["content"]) for message in messages] == [
            ("user", "Hello"),
            ("assistant", "Mock HCP response"),
        ]


class TestSessionMessageAuthority:
    """The browser supplies only message content; turn identity remains server-owned."""

    async def test_rejects_browser_turn_and_provider_fields(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_authority_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        response = await client.post(
            f"/api/v1/sessions/{created.json()['id']}/message",
            json={
                "message": "Hello",
                "turn_key": "browser-owned",
                "conversation_id": "browser-conversation",
                "agent_name": "browser-agent",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 422

    async def test_sse_keeps_text_key_messages_hint_and_done_events(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_sse_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        response = await client.post(
            f"/api/v1/sessions/{created.json()['id']}/message",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 200
        assert "SESSION_TURN_ACCEPTED" in response.text
        assert "event: text" in response.text
        assert "data: Mock HCP response" in response.text
        assert "event: key_messages" in response.text
        assert "event: hint" in response.text
        assert "event: done" in response.text

    @pytest.mark.parametrize(
        ("status", "expected_code"),
        [
            ("in_progress", "SESSION_TURN_IN_PROGRESS"),
            ("reconciling", "SESSION_TURN_RECONCILING"),
            ("failed_terminal", "SESSION_TURN_FAILED"),
        ],
    )
    async def test_maps_non_success_turn_states(self, client, status, expected_code):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token(f"message_{status}_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orchestrator = SimpleNamespace(
            run_turn=AsyncMock(return_value=TurnResult(status=status, turn_key="server-turn"))
        )

        with patch(
            "app.api.sessions._session_turn_orchestrator",
            AsyncMock(return_value=orchestrator),
        ):
            response = await client.post(
                f"/api/v1/sessions/{created.json()['id']}/message",
                json={"message": "Hello"},
                headers={"Authorization": f"Bearer {user_token}"},
            )

        assert response.status_code == 200
        assert expected_code in response.text
        assert "event: text" not in response.text
        assert "event: done" not in response.text

    @pytest.mark.parametrize(
        "error_code",
        ["SESSION_CONVERSATION_UNAVAILABLE", "SESSION_SOP_SNAPSHOT_INVALID"],
    )
    async def test_maps_orchestrator_error_without_fallback(self, client, error_code):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_error_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orchestrator = SimpleNamespace(
            run_turn=AsyncMock(
                side_effect=AppException(
                    409,
                    error_code,
                    "Session turn cannot be executed",
                )
            )
        )

        with (
            patch(
                "app.api.sessions._session_turn_orchestrator",
                AsyncMock(return_value=orchestrator),
            ),
            patch("app.api.sessions.stream_agent_response") as fallback,
        ):
            response = await client.post(
                f"/api/v1/sessions/{created.json()['id']}/message",
                json={"message": "Hello"},
                headers={"Authorization": f"Bearer {user_token}"},
            )

        assert "event: error" in response.text
        assert error_code in response.text
        fallback.assert_not_called()

    async def test_resumed_request_reuses_server_turn_key(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_resume_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orchestrator = SimpleNamespace(
            run_turn=AsyncMock(
                return_value=TurnResult(status="in_progress", turn_key="existing-server-turn")
            )
        )

        with (
            patch(
                "app.api.sessions._resolve_server_turn_key",
                AsyncMock(return_value=("existing-server-turn", True)),
            ),
            patch(
                "app.api.sessions._session_turn_orchestrator",
                AsyncMock(return_value=orchestrator),
            ),
        ):
            response = await client.post(
                f"/api/v1/sessions/{created.json()['id']}/message",
                json={"message": "Hello"},
                headers={"Authorization": f"Bearer {user_token}"},
            )

        assert "SESSION_TURN_RESUMED" in response.text
        assert "SESSION_TURN_IN_PROGRESS" in response.text
        assert orchestrator.run_turn.await_args.args[1] == "existing-server-turn"

    async def test_resumed_turn_can_replay_committed_winner_without_fallback(self, client):
        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_winner_replay_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        orchestrator = SimpleNamespace(
            run_turn=AsyncMock(
                return_value=TurnResult(
                    status="succeeded",
                    turn_key="winner-server-turn",
                    text="Committed winner",
                    response_id="resp-winner",
                )
            )
        )

        with (
            patch(
                "app.api.sessions._resolve_server_turn_key",
                AsyncMock(return_value=("winner-server-turn", True)),
            ),
            patch(
                "app.api.sessions._session_turn_orchestrator",
                AsyncMock(return_value=orchestrator),
            ),
            patch(
                "app.api.sessions._successful_turn_observables",
                AsyncMock(return_value=("[]", [])),
            ),
            patch("app.api.sessions.stream_agent_response") as fallback,
        ):
            response = await client.post(
                f"/api/v1/sessions/{created.json()['id']}/message",
                json={"message": "Hello"},
                headers={"Authorization": f"Bearer {user_token}"},
            )

        assert "SESSION_TURN_RESUMED" in response.text
        assert "data: Committed winner" in response.text
        assert "event: done" in response.text
        fallback.assert_not_called()

    async def test_unfinished_same_text_is_reused_but_terminal_same_text_is_new(self, client):
        from app.api.sessions import _resolve_server_turn_key

        admin_id, admin_token = await _create_admin_and_token()
        scenario_id = await _create_active_scenario(client, admin_id, admin_token)
        _, user_token = await _create_user_and_token("message_key_resolution_user")
        created = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        session_id = created.json()["id"]
        digest = hashlib.sha256(b"same text").hexdigest()

        async with TestSessionLocal() as db:
            pending = SessionTurn(
                session_id=session_id,
                turn_key="pending-server-turn",
                status="pending",
                input_digest=digest,
                frozen_step=0,
                frozen_context_revision=0,
                frozen_context_digest="a" * 64,
            )
            db.add(pending)
            await db.commit()
            turn_key, resumed = await _resolve_server_turn_key(db, session_id, "same text")
            assert (turn_key, resumed) == ("pending-server-turn", True)

            pending.transition_to("failed_terminal")
            await db.commit()
            new_turn_key, resumed = await _resolve_server_turn_key(db, session_id, "same text")

        assert resumed is False
        assert new_turn_key != "pending-server-turn"
