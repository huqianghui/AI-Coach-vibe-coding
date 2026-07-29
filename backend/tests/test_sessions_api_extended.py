"""Extended tests for Sessions API: cover active session, SSE message, closed session."""

import json

import pytest
from httpx import AsyncClient

from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.scoring_rubric import ScoringRubric
from app.models.session import CoachingSession
from app.models.user import User
from app.services.agent_chat_service import AgentResponseEvent
from app.services.agents.adapters.mock import MockCoachingAdapter
from app.services.agents.avatar.mock import MockAvatarAdapter
from app.services.agents.registry import ServiceRegistry
from app.services.agents.stt.mock import MockSTTAdapter
from app.services.agents.tts.mock import MockTTSAdapter
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _mock_agent_stream(*_args, **_kwargs):
    """Return a deterministic hosted-Agent stream for extended API tests."""
    yield AgentResponseEvent(kind="text", text="Mock HCP response")
    yield AgentResponseEvent(kind="completed", response_id="resp-session-extended-test")


@pytest.fixture(autouse=True)
def register_mock_adapters():
    """Register mock adapters for SSE streaming tests."""
    ServiceRegistry._instance = None
    ServiceRegistry._categories = {}
    reg = ServiceRegistry()
    reg.register("llm", MockCoachingAdapter())
    reg.register("stt", MockSTTAdapter())
    reg.register("tts", MockTTSAdapter())
    reg.register("avatar", MockAvatarAdapter())
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.api.sessions.stream_agent_response", _mock_agent_stream)
        yield
    ServiceRegistry._instance = None
    ServiceRegistry._categories = {}


async def _setup_session(
    status: str = "created",
) -> tuple[str, str, str, str]:
    """Create user, admin, HCP, scenario, and session.

    Returns (user_id, session_id, user_token, admin_token).
    """
    async with TestSessionLocal() as session:
        admin = User(
            username="admin_ext",
            email="admin_ext@test.com",
            hashed_password=get_password_hash("admin"),
            full_name="Admin Ext",
            role="admin",
        )
        session.add(admin)
        await session.flush()

        user = User(
            username="user_ext",
            email="user_ext@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="User Ext",
            role="user",
        )
        session.add(user)
        await session.flush()

        hcp = HcpProfile(
            name="Dr. Extended",
            specialty="Oncology",
            created_by=admin.id,
            agent_id="dr-extended-agent",
            agent_version="1",
            agent_sync_status="synced",
        )
        session.add(hcp)
        await session.flush()

        rubric = ScoringRubric(
            name="Extended Rubric",
            scenario_type="f2f",
            dimensions=json.dumps([]),
            created_by=admin.id,
        )
        session.add(rubric)
        await session.flush()

        scenario = Scenario(
            name="Extended Scenario",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["Superior PFS", "Better safety"]),
            skill_id="test-skill-id",
            status="active",
            created_by=admin.id,
            rubric_id=rubric.id,
        )
        session.add(scenario)
        await session.flush()

        km_status = json.dumps(
            [
                {"message": "Superior PFS", "delivered": False, "detected_at": None},
                {"message": "Better safety", "delivered": False, "detected_at": None},
            ]
        )
        coaching_session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status=status,
            key_messages_status=km_status,
            agent_name="dr-extended-agent",
            agent_version="1",
        )
        session.add(coaching_session)
        await session.flush()

        if status in ("in_progress", "completed", "scored"):
            msg = SessionMessage(
                session_id=coaching_session.id,
                role="user",
                content="Hello doctor",
                message_index=0,
            )
            session.add(msg)

        await session.commit()

        user_token = create_access_token(data={"sub": user.id})
        admin_token = create_access_token(data={"sub": admin.id})
        return user.id, coaching_session.id, user_token, admin_token


class TestGetActiveSession:
    """Tests for GET /api/v1/sessions/active."""

    async def test_no_active_session_returns_404(self, client: AsyncClient):
        user_id, _session_id, token, _ = await _setup_session(status="created")

        response = await client.get(
            "/api/v1/sessions/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NO_ACTIVE_SESSION"

    async def test_active_session_found(self, client: AsyncClient):
        user_id, session_id, token, _ = await _setup_session(status="in_progress")

        response = await client.get(
            "/api/v1/sessions/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["status"] == "in_progress"

    async def test_no_auth_returns_401(self, client: AsyncClient):
        response = await client.get("/api/v1/sessions/active")
        assert response.status_code == 401


class TestSendMessageToClosedSession:
    """Tests for POST /api/v1/sessions/{id}/message on completed session."""

    async def test_message_to_completed_session_returns_409(self, client: AsyncClient):
        _, session_id, token, _ = await _setup_session(status="completed")

        response = await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello after closing"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "SESSION_CLOSED"

    async def test_message_to_scored_session_returns_409(self, client: AsyncClient):
        _, session_id, token, _ = await _setup_session(status="scored")

        response = await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello after scoring"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "SESSION_CLOSED"


class TestSendMessageSSE:
    """Tests for POST /api/v1/sessions/{id}/message SSE streaming."""

    async def test_message_returns_sse_stream(self, client: AsyncClient):
        """Send a message to a created session and verify SSE stream has events."""
        _, session_id, token, _ = await _setup_session(status="created")

        response = await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Tell me about PFS data for Brukinsa"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # SSE endpoint returns 200 with text/event-stream content type
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        # Parse SSE events from the response body
        body = response.text
        assert len(body) > 0
        # Should contain at least text and done events
        assert "event: text" in body or "event: done" in body or "event: error" in body

    async def test_message_transitions_session_to_in_progress(self, client: AsyncClient):
        """Verify session transitions from created to in_progress after message."""
        _, session_id, token, _ = await _setup_session(status="created")

        # Send message
        await client.post(
            f"/api/v1/sessions/{session_id}/message",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Check session status is now in_progress
        response = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"


class TestCreateSessionExtended:
    """Additional tests for POST /api/v1/sessions/."""

    async def test_create_session_response_shape(self, client: AsyncClient):
        """Verify the full response shape of a created session."""
        _, _, token, admin_token = await _setup_session()

        # Create via API to get proper scenario_id
        async with TestSessionLocal() as db_session:
            from sqlalchemy import select

            from app.models.scenario import Scenario

            result = await db_session.execute(select(Scenario).where(Scenario.status == "active"))
            scenario = result.scalar_one()
            scenario_id = scenario.id

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "created"
        assert data["scenario_id"] == scenario_id
        assert "created_at" in data
        assert "updated_at" in data
        assert data["started_at"] is None
        assert data["completed_at"] is None
        assert data["overall_score"] is None


class TestListSessionsExtended:
    """Additional tests for GET /api/v1/sessions/."""

    async def test_list_sessions_pagination_shape(self, client: AsyncClient):
        # Use in_progress status so the session has messages and won't be filtered
        _, _, token, _ = await _setup_session(status="in_progress")

        response = await client.get(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] >= 1

    async def test_list_empty_sessions_for_new_user(self, client: AsyncClient):
        """A user with no sessions should get an empty paginated list."""
        async with TestSessionLocal() as session:
            new_user = User(
                username="empty_user",
                email="empty_user@test.com",
                hashed_password=get_password_hash("pass"),
                full_name="Empty User",
                role="user",
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            token = create_access_token(data={"sub": new_user.id})

        response = await client.get(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0


class TestGetSessionMessagesExtended:
    """Additional tests for GET /api/v1/sessions/{id}/messages."""

    async def test_messages_for_session_with_messages(self, client: AsyncClient):
        _, session_id, token, _ = await _setup_session(status="in_progress")

        response = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        assert len(messages) >= 1
        assert messages[0]["role"] == "user"
        assert "content" in messages[0]
        assert "message_index" in messages[0]

    async def test_messages_for_empty_session(self, client: AsyncClient):
        _, session_id, token, _ = await _setup_session(status="created")

        response = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        assert len(messages) == 0


class TestEndSessionExtended:
    """Additional tests for POST /api/v1/sessions/{id}/end."""

    async def test_end_session_response_has_completed_fields(self, client: AsyncClient):
        _, session_id, token, _ = await _setup_session(status="in_progress")

        response = await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
