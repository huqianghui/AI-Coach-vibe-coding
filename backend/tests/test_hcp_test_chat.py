"""Tests for POST /api/v1/hcp-profiles/{profile_id}/test-chat endpoint."""

from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_admin_and_token() -> tuple[str, str]:
    """Create an admin user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="admin_chat_test",
            email="admin_chat@test.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin Chat Test",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_user_and_token() -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username="user_chat_test",
            email="user_chat@test.com",
            hashed_password=get_password_hash("user123"),
            full_name="Regular Chat User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


async def _create_vl_instance(user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    from app.models.voice_live_instance import VoiceLiveInstance

    async with TestSessionLocal() as session:
        inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
        session.add(inst)
        await session.commit()
        await session.refresh(inst)
        return inst.id


async def _create_hcp_profile(client, token: str, user_id: str, agent_id: str | None = None):
    """Create an HCP profile and return its ID."""
    vl_id = await _create_vl_instance(user_id)
    resp = await client.post(
        "/api/v1/hcp-profiles",
        json={
            "name": "Dr. ChatTest",
            "specialty": "Oncology",
            "created_by": user_id,
            "voice_live_instance_id": vl_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Set agent_id directly in DB if provided (simulating agent sync)
    if agent_id:
        async with TestSessionLocal() as session:
            from sqlalchemy import text

            await session.execute(
                text(
                    "UPDATE hcp_profiles SET agent_id = :agent_id, "
                    "agent_version = '1' WHERE id = :pid"
                ),
                {"agent_id": agent_id, "pid": profile_id},
            )
            await session.commit()

    return profile_id


class TestTestChatEndpoint:
    """Tests for POST /api/v1/hcp-profiles/{profile_id}/test-chat."""

    async def test_chat_requires_admin_auth(self, client):
        """Non-admin user gets 403."""
        admin_id, admin_token = await _create_admin_and_token()
        profile_id = await _create_hcp_profile(client, admin_token, admin_id, agent_id="test-agent")

        _, user_token = await _create_user_and_token()
        response = await client.post(
            f"/api/v1/hcp-profiles/{profile_id}/test-chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    async def test_chat_requires_auth(self, client):
        """Unauthenticated request gets 401."""
        response = await client.post(
            "/api/v1/hcp-profiles/any-id/test-chat",
            json={"message": "Hello"},
        )
        assert response.status_code == 401

    async def test_chat_returns_404_for_nonexistent_profile(self, client):
        """Unknown profile_id returns 404."""
        _, token = await _create_admin_and_token()
        response = await client.post(
            "/api/v1/hcp-profiles/nonexistent-id/test-chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_chat_rejects_profile_without_agent(self, client):
        """Profile without agent_id returns 400."""
        user_id, token = await _create_admin_and_token()
        profile_id = await _create_hcp_profile(client, token, user_id, agent_id=None)

        response = await client.post(
            f"/api/v1/hcp-profiles/{profile_id}/test-chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # bad_request() raises ValidationException (422) in this codebase
        assert response.status_code == 422
        data = response.json()
        assert (
            "agent" in data.get("message", "").lower() or "sync" in data.get("message", "").lower()
        )

    @patch("app.api.hcp_profiles.agent_chat_service")
    async def test_chat_success_single_turn(self, mock_chat_svc, client):
        """Successful single-turn chat returns response_text and response_id."""
        mock_chat_svc.chat_with_agent = AsyncMock(
            return_value={
                "response_text": "Hello, I am Dr. ChatTest. How can I help?",
                "response_id": "resp-123",
                "agent_name": "test-agent",
                "agent_version": "1",
            }
        )

        user_id, token = await _create_admin_and_token()
        profile_id = await _create_hcp_profile(client, token, user_id, agent_id="test-agent")

        response = await client.post(
            f"/api/v1/hcp-profiles/{profile_id}/test-chat",
            json={"message": "Hello doctor"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_text" in data
        assert "response_id" in data
        assert data["response_text"] == "Hello, I am Dr. ChatTest. How can I help?"
        assert data["response_id"] == "resp-123"

        # Verify the service was called with correct params
        mock_chat_svc.chat_with_agent.assert_called_once()
        call_kwargs = mock_chat_svc.chat_with_agent.call_args
        assert call_kwargs[1]["agent_name"] == "test-agent"
        assert call_kwargs[1]["message"] == "Hello doctor"
        assert call_kwargs[1]["previous_response_id"] is None

    @patch("app.api.hcp_profiles.agent_chat_service")
    async def test_chat_multi_turn_passes_response_id(self, mock_chat_svc, client):
        """Multi-turn chat passes previous_response_id to service."""
        mock_chat_svc.chat_with_agent = AsyncMock(
            return_value={
                "response_text": "Follow-up response",
                "response_id": "resp-456",
                "agent_name": "test-agent",
                "agent_version": "1",
            }
        )

        user_id, token = await _create_admin_and_token()
        profile_id = await _create_hcp_profile(client, token, user_id, agent_id="test-agent")

        response = await client.post(
            f"/api/v1/hcp-profiles/{profile_id}/test-chat",
            json={
                "message": "Tell me more",
                "previous_response_id": "resp-123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        call_kwargs = mock_chat_svc.chat_with_agent.call_args
        assert call_kwargs[1]["previous_response_id"] == "resp-123"

    async def test_chat_validates_request_body(self, client):
        """Empty message body is rejected with 422."""
        user_id, token = await _create_admin_and_token()
        profile_id = await _create_hcp_profile(client, token, user_id, agent_id="test-agent")

        response = await client.post(
            f"/api/v1/hcp-profiles/{profile_id}/test-chat",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
