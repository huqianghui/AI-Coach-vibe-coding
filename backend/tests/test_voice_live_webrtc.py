"""Tests for Voice Live WebRTC session endpoint.

Verifies that POST /api/v1/voice-live/webrtc/session returns correct signaling URL,
bearer token (never raw API key), and session configuration for direct browser-to-Azure
WebRTC connections.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_user_and_token(username="webrtc_user") -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="WebRTC User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


def _mock_vl_config(model_or_deployment="gpt-4o"):
    """Create a mock ServiceConfig for azure_voice_live."""
    config = MagicMock()
    config.is_active = True
    config.model_or_deployment = model_or_deployment
    config.region = "eastus2"
    return config


def _mock_master_config(default_project="my-project"):
    """Create a mock master config."""
    master = MagicMock()
    master.default_project = default_project
    master.region = "eastus2"
    return master


def _mock_hcp_profile(agent_id="", agent_sync_status="none", voice_live_instance_id=None):
    """Create a mock HcpProfile-like object for WebRTC per-HCP tests."""
    profile = MagicMock()
    profile.agent_id = agent_id
    profile.agent_sync_status = agent_sync_status
    profile.voice_live_instance_id = voice_live_instance_id
    return profile


class TestWebRTCSessionModelMode:
    """Test WebRTC session creation in model mode (default)."""

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    async def test_create_webrtc_session_success_model_mode(
        self, mock_config_svc, mock_exchange, client
    ):
        """Model mode returns signaling URL with model param and bearer token."""
        _, token = await _create_user_and_token("webrtc_model")

        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="test-api-key-secret")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())
        mock_exchange.return_value = "bearer-token-123"

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify signaling URL
        assert (
            "wss://test.cognitiveservices.azure.com/voice-live/realtime/calls"
            in data["signaling_url"]
        )
        assert "api-version=2026-07-15" in data["signaling_url"]
        assert "model=gpt-4o" in data["signaling_url"]

        # Verify auth
        assert data["auth_token"] == "bearer-token-123"
        assert data["auth_type"] == "bearer"

        # Verify mode
        assert data["mode"] == "model"
        assert data["model"] == "gpt-4o"

        # Verify session_config
        assert "voice" in data["session_config"]
        assert "turn_detection" in data["session_config"]
        assert data["session_config"]["voice"]["name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert data["session_config"]["turn_detection"]["type"] == "server_vad"

        # Verify avatar warning
        assert data["avatar_warning"] is not None
        assert "not supported" in data["avatar_warning"]

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    async def test_signaling_url_uses_calls_path(self, mock_config_svc, mock_exchange, client):
        """Verify URL path is /voice-live/realtime/calls NOT /voice-live/realtime."""
        _, token = await _create_user_and_token("webrtc_calls_path")

        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="key-123")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())
        mock_exchange.return_value = "token-xyz"

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "realtime/calls?" in data["signaling_url"]
        # Should NOT be the plain /realtime endpoint
        assert "/realtime?" not in data["signaling_url"].replace("/realtime/calls?", "")


class TestWebRTCSessionAgentMode:
    """Test WebRTC session creation in agent mode."""

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    async def test_create_webrtc_session_success_agent_mode(
        self, mock_config_svc, mock_exchange, client
    ):
        """Agent mode returns signaling URL with agent_id param."""
        _, token = await _create_user_and_token("webrtc_agent")

        agent_config = '{"mode": "agent", "agent_id": "agent-abc", "project_name": "proj-1"}'
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config(agent_config))
        mock_config_svc.get_effective_key = AsyncMock(return_value="key-456")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())
        mock_exchange.return_value = "agent-bearer-token"

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["mode"] == "agent"
        assert data["agent_id"] == "agent-abc"
        assert "agent_id=agent-abc" in data["signaling_url"]
        assert "project_id=proj-1" in data["signaling_url"]
        assert data["model"] == ""  # Empty for agent mode


class TestWebRTCSessionPinnedTraining:
    """Session-bound requests use only the owned immutable Agent pin."""

    async def test_session_id_requires_authenticated_user_context(self):
        """Direct service callers cannot resolve a training pin without user identity."""
        from app.services.voice_live_webrtc import create_webrtc_session_config
        from app.utils.exceptions import AppException

        try:
            await create_webrtc_session_config(AsyncMock(), session_id="training-session")
        except AppException as exc:
            assert exc.status_code == 401
            assert exc.code == "AUTHENTICATION_REQUIRED"
        else:
            raise AssertionError("Missing user context must be rejected")

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    @patch("app.services.hcp_profile_service.get_hcp_profile")
    @patch("app.services.voice_live_websocket._resolve_training_session_context")
    async def test_exact_pin_and_version_are_signaled_before_token_exchange(
        self, mock_context, mock_get_profile, mock_config_svc, mock_exchange, client
    ):
        user_id, token = await _create_user_and_token("webrtc_pinned")
        mock_context.return_value = {
            "hcp_profile_id": "trusted-hcp",
            "agent_name": "pinned agent/name",
            "agent_version": "0042+beta",
            "avatar_enabled": False,
        }
        latest = _mock_hcp_profile(agent_id="latest-agent", agent_sync_status="failed")
        mock_get_profile.return_value = latest
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="secret-key")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(
            return_value=_mock_master_config("project / pinned")
        )
        mock_exchange.return_value = "bearer-token"
        with patch("app.services.voice_live_instance_service.resolve_voice_config") as resolve:
            resolve.return_value = {
                "voice_name": "en-US-AvaNeural",
                "voice_type": "azure-standard",
                "turn_detection_type": "server_vad",
                "noise_suppression": False,
                "echo_cancellation": False,
                "voice_live_model": "gpt-4o",
            }
            response = await client.post(
                "/api/v1/voice-live/webrtc/session",
                params={
                    "session_id": "owned-session",
                    "hcp_profile_id": "attacker-hcp",
                    "vl_instance_id": "attacker-instance",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        query = parse_qs(urlparse(data["signaling_url"]).query)
        assert query == {
            "api-version": ["2026-07-15"],
            "agent_name": ["pinned agent/name"],
            "agent_version": ["0042+beta"],
            "project_name": ["project / pinned"],
        }
        assert data["agent_id"] == "pinned agent/name"
        assert data["agent_version"] == "0042+beta"
        mock_context.assert_awaited_once_with(ANY, "owned-session", user_id)
        mock_exchange.assert_awaited_once()

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_websocket._resolve_training_session_context")
    async def test_invalid_or_foreign_session_rejects_before_token_exchange(
        self, mock_context, mock_exchange, client
    ):
        from app.utils.exceptions import AppException

        _, token = await _create_user_and_token("webrtc_foreign")
        mock_context.side_effect = AppException(
            status_code=403, code="FORBIDDEN", message="Not owned"
        )

        response = await client.post(
            "/api/v1/voice-live/webrtc/session",
            params={"session_id": "foreign-session"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
        mock_exchange.assert_not_called()

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    @patch("app.services.voice_live_websocket._resolve_training_session_context")
    async def test_training_session_rejects_missing_agent_project_before_token_exchange(
        self, mock_context, mock_config_svc, mock_exchange
    ):
        """A pinned training Agent cannot silently signal without its project."""
        from app.services.voice_live_webrtc import create_webrtc_session_config
        from app.utils.exceptions import AppException

        mock_context.return_value = {
            "hcp_profile_id": "trusted-hcp",
            "agent_name": "pinned-agent",
            "agent_version": "7",
            "avatar_enabled": False,
        }
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="secret-key")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config(" "))

        try:
            await create_webrtc_session_config(
                AsyncMock(), session_id="training-session", user_id="owner-1"
            )
        except AppException as exc:
            assert exc.status_code == 409
            assert exc.code == "AGENT_PROJECT_MISSING"
        else:
            raise AssertionError("Missing Agent project must be rejected")
        mock_exchange.assert_not_awaited()


class TestWebRTCSessionAgentSyncGate:
    """Test D-05 auto-resync and D-08 forced-agent-mode enforcement for HCP profiles."""

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    @patch("app.services.hcp_profile_service.get_hcp_profile")
    async def test_unsynced_hcp_rejects_with_409(
        self, mock_get_profile, mock_config_svc, mock_exchange, client
    ):
        """HCP with no synced agent is rejected before any session is built."""
        _, token = await _create_user_and_token("webrtc_unsynced")

        mock_get_profile.return_value = _mock_hcp_profile(agent_id="", agent_sync_status="none")
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="key-789")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            params={"hcp_profile_id": "hcp-unsynced-1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["code"] == "AGENT_SYNC_REQUIRED"
        mock_exchange.assert_not_called()

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    @patch("app.services.agent_sync_service.resync_classic_agent")
    @patch("app.services.hcp_profile_service.get_hcp_profile")
    async def test_classic_agent_auto_resyncs_then_succeeds(
        self, mock_get_profile, mock_resync, mock_config_svc, mock_exchange, client
    ):
        """Classic asst_* agent is resynced to hosted before the signaling URL is built."""
        _, token = await _create_user_and_token("webrtc_resync")

        profile = _mock_hcp_profile(agent_id="asst_legacy_webrtc", agent_sync_status="synced")
        mock_get_profile.return_value = profile

        async def _fake_resync(db, p):
            p.agent_id = "hosted-legacy-webrtc"
            p.agent_sync_status = "synced"
            return True

        mock_resync.side_effect = _fake_resync
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value="key-abc")
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())
        mock_exchange.return_value = "resynced-bearer-token"

        with patch("app.services.voice_live_instance_service.resolve_voice_config") as mock_resolve:
            mock_resolve.return_value = {
                "voice_name": "en-US-AvaNeural",
                "voice_type": "azure-standard",
                "turn_detection_type": "server_vad",
                "noise_suppression": False,
                "echo_cancellation": False,
                "voice_live_model": "gpt-4o",
            }
            resp = await client.post(
                "/api/v1/voice-live/webrtc/session",
                params={"hcp_profile_id": "hcp-resync-1"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        mock_resync.assert_awaited_once()
        assert data["agent_id"] == "hosted-legacy-webrtc"
        assert "agent_id=hosted-legacy-webrtc" in data["signaling_url"]


class TestWebRTCSessionErrors:
    """Test error cases for WebRTC session endpoint."""

    @patch("app.services.voice_live_webrtc.config_service")
    async def test_create_webrtc_session_not_configured(self, mock_config_svc, client):
        """Returns 503 when Voice Live is not configured."""
        _, token = await _create_user_and_token("webrtc_noconfig")

        mock_config_svc.get_config = AsyncMock(return_value=None)

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503
        data = resp.json()
        assert data["code"] == "WEBRTC_SESSION_FAILED"
        assert "not configured" in data["message"].lower()

    async def test_create_webrtc_session_requires_auth(self, client):
        """Returns 401 when no JWT token provided."""
        resp = await client.post("/api/v1/voice-live/webrtc/session")
        assert resp.status_code == 401


class TestWebRTCSessionSecurity:
    """Test security properties of WebRTC session endpoint."""

    @patch("app.services.voice_live_webrtc._exchange_api_key_for_bearer_token")
    @patch("app.services.voice_live_webrtc.config_service")
    async def test_api_key_never_in_response(self, mock_config_svc, mock_exchange, client):
        """Raw API key must never appear in any response field."""
        _, token = await _create_user_and_token("webrtc_security")

        secret_api_key = "super-secret-api-key-12345"
        mock_config_svc.get_config = AsyncMock(return_value=_mock_vl_config("gpt-4o"))
        mock_config_svc.get_effective_key = AsyncMock(return_value=secret_api_key)
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.cognitiveservices.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=_mock_master_config())
        mock_exchange.return_value = "safe-bearer-token"

        resp = await client.post(
            "/api/v1/voice-live/webrtc/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        response_text = resp.text

        # API key must not appear anywhere in the response
        assert secret_api_key not in response_text

        # Auth token should be the bearer token, not the API key
        data = resp.json()
        assert data["auth_token"] == "safe-bearer-token"
        assert data["auth_token"] != secret_api_key
