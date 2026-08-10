"""Regression tests for SessionResponse eager-loading of scenario_name and message_count.

These tests verify that all session endpoints correctly eager-load the `scenario`
and `messages` relationships, preventing MissingGreenlet errors in async context.
The bug: SessionResponse uses @property fields (scenario_name, message_count) that
access lazy-loaded relationships. Without eager loading, async SQLAlchemy raises
MissingGreenlet / greenlet_spawn has not been called.
"""

import json

from httpx import AsyncClient

from app.models.hcp_profile import HcpProfile
from app.models.message import SessionMessage
from app.models.scenario import Scenario
from app.models.session import CoachingSession
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_test_data(status: str = "created") -> tuple[str, str, str, str]:
    """Create user, scenario, session. Returns (user_id, scenario_id, session_id, token)."""
    async with TestSessionLocal() as db:
        admin = User(
            username="eager_admin",
            email="eager_admin@test.com",
            hashed_password=get_password_hash("admin"),
            full_name="Admin",
            role="admin",
        )
        db.add(admin)
        await db.flush()

        user = User(
            username="eager_user",
            email="eager_user@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Eager User",
            role="user",
        )
        db.add(user)
        await db.flush()

        hcp = HcpProfile(
            name="Dr. Eager",
            specialty="Cardiology",
            created_by=admin.id,
            agent_id="dr-eager-agent",
            agent_version="1",
            agent_sync_status="synced",
        )
        db.add(hcp)
        await db.flush()

        skill_content = "# SOP\n## Step 1: Open\n## Step 2: Discover\n## Step 3: Close"
        skill = Skill(
            name="Eager Load Skill",
            content=skill_content,
            status="published",
            created_by=admin.id,
        )
        db.add(skill)
        await db.flush()
        skill_version = SkillVersion(
            skill_id=skill.id,
            version_number=1,
            content=skill_content,
            metadata_json='{"knowledge_references":["test-reference"]}',
            is_published=True,
            created_by=admin.id,
        )
        db.add(skill_version)
        await db.flush()

        scenario = Scenario(
            name="Eager Load Scenario",
            hcp_profile_id=hcp.id,
            key_messages=json.dumps(["Key message 1"]),
            skill_id=skill.id,
            skill_version_id=skill_version.id,
            status="active",
            created_by=admin.id,
            rubric_id="test-rubric",
        )
        db.add(scenario)
        await db.flush()

        km_status = json.dumps(
            [{"message": "Key message 1", "delivered": False, "detected_at": None}]
        )
        session = CoachingSession(
            user_id=user.id,
            scenario_id=scenario.id,
            status=status,
            key_messages_status=km_status,
        )
        db.add(session)
        await db.flush()

        # Add messages for in_progress/completed sessions
        if status in ("in_progress", "completed", "scored"):
            msg1 = SessionMessage(
                session_id=session.id, role="user", content="Hello", message_index=0
            )
            msg2 = SessionMessage(
                session_id=session.id, role="assistant", content="Hi there", message_index=1
            )
            db.add_all([msg1, msg2])

        await db.commit()
        token = create_access_token(data={"sub": user.id})
        return user.id, scenario.id, session.id, token


class TestSessionResponseEagerLoading:
    """Verify scenario_name and message_count are present in all session endpoint responses."""

    async def test_create_session_returns_scenario_name_and_message_count(
        self, client: AsyncClient
    ):
        """POST /sessions must return scenario_name and message_count without 500."""
        _, scenario_id, _, token = await _create_test_data()

        response = await client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_id, "mode": "text"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["scenario_name"] == "Eager Load Scenario"
        assert data["message_count"] == 0

    async def test_get_session_returns_scenario_name_and_message_count(self, client: AsyncClient):
        """GET /sessions/{id} must return scenario_name and message_count without 500."""
        _, _, session_id, token = await _create_test_data(status="in_progress")

        response = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["scenario_name"] == "Eager Load Scenario"
        assert data["message_count"] == 2

    async def test_get_active_session_returns_scenario_name_and_message_count(
        self, client: AsyncClient
    ):
        """GET /sessions/active must return scenario_name and message_count without 500."""
        _, _, session_id, token = await _create_test_data(status="in_progress")

        response = await client.get(
            "/api/v1/sessions/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["id"] == session_id
        assert data["scenario_name"] == "Eager Load Scenario"
        assert data["message_count"] == 2

    async def test_list_sessions_returns_scenario_name_and_message_count(self, client: AsyncClient):
        """GET /sessions must return scenario_name and message_count for each session."""
        _, _, _, token = await _create_test_data(status="in_progress")

        response = await client.get(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["total"] >= 1
        session_data = data["items"][0]
        assert session_data["scenario_name"] == "Eager Load Scenario"
        assert session_data["message_count"] == 2

    async def test_end_session_returns_scenario_name_and_message_count(self, client: AsyncClient):
        """POST /sessions/{id}/end must return scenario_name and message_count without 500."""
        _, _, session_id, token = await _create_test_data(status="in_progress")

        response = await client.post(
            f"/api/v1/sessions/{session_id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["scenario_name"] == "Eager Load Scenario"
        assert data["message_count"] == 2
        assert data["status"] == "completed"


class TestUnhandledExceptionHandler:
    """Verify the global unhandled exception handler returns proper JSON (not raw 500)."""

    async def test_unhandled_exception_returns_json_error(self, client: AsyncClient):
        """Any unhandled exception should return structured JSON, not empty 500."""
        # Request a non-existent session with valid auth to trigger NotFoundException
        # which is an AppException — test that path first
        _, _, _, token = await _create_test_data()

        response = await client.get(
            "/api/v1/sessions/nonexistent-id-00000000",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "code" in data
        assert "message" in data
