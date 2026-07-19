"""Tests for Voice Live per-HCP voice/avatar settings (Phase 12).

Verifies that get_voice_live_token returns per-HCP voice/avatar settings
when hcp_profile_id is provided, falls back to defaults otherwise,
and handles errors gracefully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from app.models.hcp_profile import HcpProfile
    from app.models.service_config import ServiceConfig

from app.models.user import User
from app.schemas.voice_live import VoiceLiveTokenResponse
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_user_and_token(username="vlhcp_user") -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="VL HCP User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


def _make_mock_vl_config():
    """Create a mock voice_live config object."""
    mock = MagicMock()
    mock.is_active = True
    mock.endpoint = "https://test.openai.azure.com"
    mock.region = "eastus2"
    mock.model_or_deployment = "gpt-4o-realtime-preview"
    mock.api_key_encrypted = ""
    return mock


def _make_mock_avatar_config():
    """Create a mock avatar config object."""
    mock = MagicMock()
    mock.is_active = True
    mock.model_or_deployment = "Lisa-casual-sitting"
    return mock


def _make_mock_hcp_profile():
    """Create a mock HCP profile with per-HCP voice/avatar settings."""
    profile = MagicMock()
    profile.agent_id = "asst_test123"
    profile.agent_sync_status = "synced"
    # VoiceLiveInstance reference — None to use inline fields (fallback path)
    profile.voice_live_instance_id = None
    profile.voice_live_instance = None
    # Voice Live flags
    profile.voice_live_enabled = True
    profile.voice_live_model = "gpt-4o-realtime-preview"
    # Voice settings
    profile.voice_name = "zh-CN-YunxiNeural"
    profile.voice_type = "azure-standard"
    profile.voice_temperature = 0.7
    profile.voice_custom = False
    # Avatar settings
    profile.avatar_character = "harry"
    profile.avatar_style = "business"
    profile.avatar_customized = False
    # Conversation parameters
    profile.turn_detection_type = "azure_semantic_vad"
    profile.noise_suppression = True
    profile.echo_cancellation = False
    profile.eou_detection = False
    profile.recognition_language = "zh-CN"
    profile.agent_instructions_override = ""
    return profile


class TestPerHcpTokenBroker:
    """Tests for get_voice_live_token with per-HCP voice/avatar settings."""

    @pytest.mark.asyncio
    async def test_token_returns_per_hcp_voice_settings(self):
        """get_voice_live_token returns per-HCP voice settings when hcp_profile_id provided."""
        from app.services.voice_live_service import get_voice_live_token

        mock_db = AsyncMock()
        mock_profile = _make_mock_hcp_profile()

        mock_config_svc_calls = {
            "azure_voice_live": _make_mock_vl_config(),
            "azure_avatar": _make_mock_avatar_config(),
        }

        with (
            patch(
                "app.services.voice_live_service.config_service.get_config",
                new_callable=AsyncMock,
                side_effect=lambda db, name: mock_config_svc_calls.get(name),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_key",
                new_callable=AsyncMock,
                side_effect=lambda db, name: (
                    "test-key" if name == "azure_voice_live" else "avatar-key"
                ),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_endpoint",
                new_callable=AsyncMock,
                return_value="https://test.openai.azure.com",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_master_config",
                new_callable=AsyncMock,
                return_value=MagicMock(region="eastus2", default_project="test-project"),
            ),
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
        ):
            result = await get_voice_live_token(db=mock_db, hcp_profile_id="test-hcp-id")

        assert result.voice_name == "zh-CN-YunxiNeural"
        assert result.avatar_character == "harry"
        assert result.avatar_style == "business"
        assert result.voice_temperature == 0.7
        assert result.turn_detection_type == "azure_semantic_vad"
        assert result.noise_suppression is True
        assert result.recognition_language == "zh-CN"
        # Agent mode: token masked, auth_type = bearer
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"

    @pytest.mark.asyncio
    async def test_token_returns_defaults_when_no_hcp_profile_id(self):
        """get_voice_live_token returns defaults when no hcp_profile_id provided."""
        from app.services.voice_live_service import get_voice_live_token

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.voice_live_service.config_service.get_config",
                new_callable=AsyncMock,
                side_effect=lambda db, name: (
                    _make_mock_vl_config() if name == "azure_voice_live" else None
                ),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_key",
                new_callable=AsyncMock,
                side_effect=lambda db, name: "test-key" if name == "azure_voice_live" else "",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_endpoint",
                new_callable=AsyncMock,
                return_value="https://test.openai.azure.com",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_master_config",
                new_callable=AsyncMock,
                return_value=MagicMock(region="eastus2", default_project="test-project"),
            ),
        ):
            result = await get_voice_live_token(db=mock_db, hcp_profile_id=None)

        # Should get global defaults, not per-HCP settings
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.turn_detection_type == "server_vad"
        assert result.noise_suppression is False
        assert result.echo_cancellation is False

    @pytest.mark.asyncio
    async def test_token_falls_back_on_hcp_service_exception(self):
        """get_voice_live_token falls back to defaults when hcp_profile_service raises."""
        from app.services.voice_live_service import get_voice_live_token

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.voice_live_service.config_service.get_config",
                new_callable=AsyncMock,
                side_effect=lambda db, name: (
                    _make_mock_vl_config() if name == "azure_voice_live" else None
                ),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_key",
                new_callable=AsyncMock,
                side_effect=lambda db, name: "test-key" if name == "azure_voice_live" else "",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_endpoint",
                new_callable=AsyncMock,
                return_value="https://test.openai.azure.com",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_master_config",
                new_callable=AsyncMock,
                return_value=MagicMock(region="eastus2", default_project="test-project"),
            ),
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                side_effect=Exception("Profile not found"),
            ),
        ):
            # Should not crash, should return defaults
            result = await get_voice_live_token(db=mock_db, hcp_profile_id="nonexistent")

        # Defaults should be used
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.turn_detection_type == "server_vad"
        assert result.noise_suppression is False

    @pytest.mark.asyncio
    async def test_token_returns_per_hcp_agent_id_in_agent_mode(self):
        """get_voice_live_token returns per-HCP agent_id when in agent mode."""
        import json

        from app.services.voice_live_service import get_voice_live_token

        mock_db = AsyncMock()
        mock_profile = _make_mock_hcp_profile()
        mock_profile.agent_id = "per-hcp-agent-id"

        # Agent mode config
        mock_vl_config = _make_mock_vl_config()
        mock_vl_config.model_or_deployment = json.dumps(
            {
                "mode": "agent",
                "agent_id": "config-level-agent-id",
                "project_name": "test-project",
            }
        )

        with (
            patch(
                "app.services.voice_live_service.config_service.get_config",
                new_callable=AsyncMock,
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else _make_mock_avatar_config()
                ),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_key",
                new_callable=AsyncMock,
                side_effect=lambda db, name: (
                    "test-key" if name == "azure_voice_live" else "avatar-key"
                ),
            ),
            patch(
                "app.services.voice_live_service.config_service.get_effective_endpoint",
                new_callable=AsyncMock,
                return_value="https://test.openai.azure.com",
            ),
            patch(
                "app.services.voice_live_service.config_service.get_master_config",
                new_callable=AsyncMock,
                return_value=MagicMock(region="eastus2", default_project="master-default-project"),
            ),
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
        ):
            result = await get_voice_live_token(db=mock_db, hcp_profile_id="test-hcp-id")

        # Should use per-HCP agent_id, not config-level
        assert result.agent_id == "per-hcp-agent-id"
        # When HCP profile overrides agent, project_name comes from master default_project
        assert result.project_name == "master-default-project"
        # Agent mode: token masked, auth_type = bearer
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"


class TestVoiceLiveTokenResponseSchema:
    """Tests for VoiceLiveTokenResponse schema with per-HCP fields."""

    async def test_schema_includes_per_hcp_fields(self):
        """VoiceLiveTokenResponse includes all per-HCP voice/avatar fields."""
        resp = VoiceLiveTokenResponse(
            endpoint="https://example.openai.azure.com",
            token="test-key",
            region="eastus2",
            model="gpt-4o-realtime-preview",
            avatar_enabled=True,
            avatar_character="harry",
            voice_name="zh-CN-YunxiNeural",
            avatar_style="business",
            avatar_customized=False,
            voice_type="azure-standard",
            voice_temperature=0.7,
            voice_custom=False,
            turn_detection_type="azure_semantic_vad",
            noise_suppression=True,
            echo_cancellation=False,
            eou_detection=False,
            recognition_language="zh-CN",
        )
        assert resp.avatar_style == "business"
        assert resp.voice_temperature == 0.7
        assert resp.turn_detection_type == "azure_semantic_vad"
        assert resp.noise_suppression is True
        assert resp.recognition_language == "zh-CN"

    async def test_schema_defaults_for_per_hcp_fields(self):
        """VoiceLiveTokenResponse has correct defaults for per-HCP fields."""
        resp = VoiceLiveTokenResponse(
            endpoint="https://example.openai.azure.com",
            token="test-key",
            region="eastus2",
            model="gpt-4o-realtime-preview",
            avatar_enabled=False,
            avatar_character="lori",
            voice_name="en-US-AvaNeural",
        )
        assert resp.avatar_style == "casual"
        assert resp.voice_type == "azure-standard"
        assert resp.voice_temperature == 0.9
        assert resp.voice_custom is False
        assert resp.turn_detection_type == "server_vad"
        assert resp.noise_suppression is False
        assert resp.echo_cancellation is False
        assert resp.eou_detection is False
        assert resp.recognition_language == "auto"


class TestVoiceLiveAPIWithHcpProfileId:
    """Tests for Voice Live API endpoint accepting hcp_profile_id query param."""

    @patch("app.services.voice_live_service.config_service")
    async def test_token_endpoint_accepts_hcp_profile_id(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token?hcp_profile_id=test-id returns 200 or 503."""
        mock_config_svc.get_config = AsyncMock(return_value=None)
        mock_config_svc.get_effective_key = AsyncMock(return_value="")
        mock_config_svc.get_effective_endpoint = AsyncMock(return_value="")
        mock_config_svc.get_master_config = AsyncMock(return_value=None)

        _, token = await _create_user_and_token("vl_hcp_query")
        response = await client.post(
            "/api/v1/voice-live/token?hcp_profile_id=test-hcp-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 503 because no config exists, but the endpoint accepts the param
        assert response.status_code == 503

    @patch("app.services.voice_live_service.config_service")
    async def test_token_endpoint_with_hcp_and_config(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token?hcp_profile_id returns per-HCP settings."""
        mock_vl_config = _make_mock_vl_config()
        mock_profile = _make_mock_hcp_profile()

        mock_config_svc.get_config = AsyncMock(
            side_effect=lambda db, name: mock_vl_config if name == "azure_voice_live" else None
        )
        mock_config_svc.get_effective_key = AsyncMock(
            side_effect=lambda db, name: "test-api-key" if name == "azure_voice_live" else ""
        )
        mock_config_svc.get_effective_endpoint = AsyncMock(
            return_value="https://test.openai.azure.com"
        )
        mock_config_svc.get_master_config = AsyncMock(
            return_value=MagicMock(region="eastus2", default_project="test-project")
        )

        _, token = await _create_user_and_token("vl_hcp_config")
        with patch(
            "app.services.hcp_profile_service.get_hcp_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            response = await client.post(
                "/api/v1/voice-live/token?hcp_profile_id=test-hcp-id",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["voice_name"] == "zh-CN-YunxiNeural"
        assert data["avatar_character"] == "harry"
        assert data["avatar_style"] == "business"
        assert data["voice_temperature"] == 0.7
        assert data["turn_detection_type"] == "azure_semantic_vad"
        assert data["noise_suppression"] is True


# ---------------------------------------------------------------------------
# Real-data integration tests (no mocking of config_service / hcp_profile_service)
# ---------------------------------------------------------------------------


async def _seed_user(session, username="realdata_user") -> str:
    """Create a user in the test DB and return its id."""
    user = User(
        username=username,
        email=f"{username}@real.test",
        hashed_password=get_password_hash("pass"),
        full_name="Real Data User",
        role="user",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user.id


async def _seed_master_config(session, user_id: str) -> ServiceConfig:
    """Seed an AI Foundry master config row with encrypted test key."""
    from app.models.service_config import ServiceConfig
    from app.utils.encryption import encrypt_value

    master = ServiceConfig(
        service_name="ai_foundry",
        display_name="Azure AI Foundry",
        endpoint="https://test-foundry.services.ai.azure.com",
        api_key_encrypted=encrypt_value("test-master-api-key-12345"),
        model_or_deployment="",
        region="eastus2",
        default_project="test-project",
        is_master=True,
        is_active=True,
        updated_by=user_id,
    )
    session.add(master)
    await session.flush()
    return master


async def _seed_voice_live_config(
    session, user_id: str, model_or_deployment: str = "gpt-4o-realtime-preview"
) -> ServiceConfig:
    """Seed an azure_voice_live service config row."""
    from app.models.service_config import ServiceConfig
    from app.utils.encryption import encrypt_value

    vl = ServiceConfig(
        service_name="azure_voice_live",
        display_name="Azure Voice Live",
        endpoint="https://test.openai.azure.com",
        api_key_encrypted=encrypt_value("test-vl-api-key-67890"),
        model_or_deployment=model_or_deployment,
        region="eastus2",
        is_master=False,
        is_active=True,
        updated_by=user_id,
    )
    session.add(vl)
    await session.flush()
    return vl


async def _seed_avatar_config(session, user_id: str) -> ServiceConfig:
    """Seed an azure_avatar service config row."""
    from app.models.service_config import ServiceConfig
    from app.utils.encryption import encrypt_value

    avatar = ServiceConfig(
        service_name="azure_avatar",
        display_name="Azure Avatar",
        endpoint="",
        api_key_encrypted=encrypt_value("test-avatar-key-99999"),
        model_or_deployment="Lisa-casual-sitting",
        region="",
        is_master=False,
        is_active=True,
        updated_by=user_id,
    )
    session.add(avatar)
    await session.flush()
    return avatar


async def _seed_hcp_profile(session, user_id: str, **overrides) -> HcpProfile:
    """Seed an HcpProfile with per-HCP voice/avatar settings.

    D-09: HcpProfile no longer has inline voice/avatar columns -- per-HCP
    voice/avatar config now comes exclusively from a linked VoiceLiveInstance.
    This helper creates a VoiceLiveInstance carrying the settings previously
    passed as inline HcpProfile kwargs and links it via voice_live_instance_id.
    """
    from app.models.hcp_profile import HcpProfile
    from app.models.voice_live_instance import VoiceLiveInstance

    vl_instance_overrides = {
        k: overrides.pop(k)
        for k in list(overrides)
        if k
        in {
            "voice_live_model",
            "voice_name",
            "voice_type",
            "voice_temperature",
            "voice_custom",
            "avatar_character",
            "avatar_style",
            "avatar_customized",
            "turn_detection_type",
            "noise_suppression",
            "echo_cancellation",
            "eou_detection",
            "recognition_language",
        }
    }
    # Drop legacy flag kwarg if any caller still passes it -- no longer a real field.
    overrides.pop("voice_live_enabled", None)

    vl_defaults = dict(
        name="Per-HCP Real Data Instance",
        created_by=user_id,
        voice_live_model="gpt-4o-realtime-preview",
        voice_name="zh-CN-YunxiNeural",
        voice_type="azure-standard",
        voice_temperature=0.7,
        voice_custom=False,
        avatar_character="harry",
        avatar_style="business",
        avatar_customized=False,
        turn_detection_type="azure_semantic_vad",
        noise_suppression=True,
        echo_cancellation=False,
        eou_detection=False,
        recognition_language="zh-CN",
    )
    vl_defaults.update(vl_instance_overrides)
    vl_instance = VoiceLiveInstance(**vl_defaults)
    session.add(vl_instance)
    await session.flush()

    defaults = dict(
        name="Dr. RealData Chen",
        specialty="Oncology",
        created_by=user_id,
        agent_id="asst_real_test_agent",
        agent_sync_status="synced",
        voice_live_instance_id=vl_instance.id,
    )
    defaults.update(overrides)
    profile = HcpProfile(**defaults)
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    profile.voice_live_instance = vl_instance
    return profile


class TestPerHcpTokenBrokerRealData:
    """Real-data integration tests for get_voice_live_token — no mocking.

    Seeds ServiceConfig + HcpProfile rows into the in-memory test DB and calls
    get_voice_live_token with a real async session so that config_service and
    hcp_profile_service query real data.
    """

    @pytest.mark.asyncio
    async def test_token_returns_per_hcp_voice_settings_real_db(self, db_session):
        """get_voice_live_token returns per-HCP voice settings from real DB data."""
        from app.services.voice_live_service import get_voice_live_token

        user_id = await _seed_user(db_session, "real_hcp_voice")
        await _seed_master_config(db_session, user_id)
        await _seed_voice_live_config(db_session, user_id)
        await _seed_avatar_config(db_session, user_id)
        profile = await _seed_hcp_profile(db_session, user_id)
        await db_session.commit()

        result = await get_voice_live_token(db=db_session, hcp_profile_id=profile.id)

        assert result.voice_name == "zh-CN-YunxiNeural"
        assert result.avatar_character == "harry"
        assert result.avatar_style == "business"
        assert result.voice_temperature == 0.7
        assert result.turn_detection_type == "azure_semantic_vad"
        assert result.noise_suppression is True
        assert result.recognition_language == "zh-CN"
        # Agent mode: profile has synced agent_id
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"
        assert result.agent_id == "asst_real_test_agent"

    @pytest.mark.asyncio
    async def test_token_returns_defaults_when_no_hcp_profile_id_real_db(self, db_session):
        """get_voice_live_token returns defaults from real DB when no hcp_profile_id."""
        from app.services.voice_live_service import get_voice_live_token

        user_id = await _seed_user(db_session, "real_no_hcp")
        await _seed_master_config(db_session, user_id)
        await _seed_voice_live_config(db_session, user_id)
        await db_session.commit()

        result = await get_voice_live_token(db=db_session, hcp_profile_id=None)

        # Global defaults (no HCP override)
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.turn_detection_type == "server_vad"
        assert result.noise_suppression is False
        assert result.echo_cancellation is False

    @pytest.mark.asyncio
    async def test_token_returns_per_hcp_agent_id_in_agent_mode_real_db(self, db_session):
        """get_voice_live_token returns per-HCP agent_id from real DB in agent mode."""
        import json

        from app.services.voice_live_service import get_voice_live_token

        user_id = await _seed_user(db_session, "real_agent_mode")
        await _seed_master_config(db_session, user_id)

        # Config-level model_or_deployment indicates agent mode with a config-level agent_id
        agent_config = json.dumps(
            {
                "mode": "agent",
                "agent_id": "asst_config_level_agent",
                "project_name": "config-project",
            }
        )
        await _seed_voice_live_config(db_session, user_id, model_or_deployment=agent_config)
        await _seed_avatar_config(db_session, user_id)

        # HCP profile has its own agent_id that should override
        profile = await _seed_hcp_profile(
            db_session,
            user_id,
            agent_id="asst_per_hcp_agent",
            agent_sync_status="synced",
        )
        await db_session.commit()

        result = await get_voice_live_token(db=db_session, hcp_profile_id=profile.id)

        # Per-HCP agent_id overrides config-level
        assert result.agent_id == "asst_per_hcp_agent"
        # project_name comes from master default_project when HCP overrides
        assert result.project_name == "test-project"
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"

    @pytest.mark.asyncio
    async def test_token_with_no_config_raises_real_db(self, db_session):
        """get_voice_live_token raises ValueError when no config exists in real DB."""
        from app.services.voice_live_service import get_voice_live_token

        # Empty DB — no service configs at all
        with pytest.raises(ValueError, match="Voice Live not configured"):
            await get_voice_live_token(db=db_session, hcp_profile_id=None)

    @pytest.mark.asyncio
    async def test_token_fallback_when_profile_has_no_agent_real_db(self, db_session):
        """get_voice_live_token falls back to config-level agent when profile has none."""
        import json

        from app.services.voice_live_service import get_voice_live_token

        user_id = await _seed_user(db_session, "real_no_agent_profile")
        await _seed_master_config(db_session, user_id)

        agent_config = json.dumps(
            {
                "mode": "agent",
                "agent_id": "asst_config_fallback",
                "project_name": "fallback-project",
            }
        )
        await _seed_voice_live_config(db_session, user_id, model_or_deployment=agent_config)

        # Profile with no agent_id
        profile = await _seed_hcp_profile(
            db_session,
            user_id,
            agent_id="",
            agent_sync_status="none",
        )
        await db_session.commit()

        result = await get_voice_live_token(db=db_session, hcp_profile_id=profile.id)

        # Falls back to config-level agent_id
        assert result.agent_id == "asst_config_fallback"
        assert result.project_name == "fallback-project"


class TestVoiceLiveAPIWithHcpProfileIdRealData:
    """Real-data API tests for Voice Live token endpoint — no config_service mocking.

    Seeds real ServiceConfig + HcpProfile in the test DB and exercises the
    /api/v1/voice-live/token endpoint through the HTTP client.
    """

    async def test_token_endpoint_returns_503_with_empty_db(self, client):
        """POST /api/v1/voice-live/token returns 503 when DB has no voice live config."""
        _, token = await _create_user_and_token("vl_empty_db")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 503

    async def test_token_endpoint_with_real_config_and_hcp(self, client):
        """POST /api/v1/voice-live/token?hcp_profile_id returns per-HCP settings from real DB."""
        # Seed data via TestSessionLocal (same DB as the client uses)
        async with TestSessionLocal() as session:
            user_id = await _seed_user(session, "vl_real_api_user")
            await _seed_master_config(session, user_id)
            await _seed_voice_live_config(session, user_id)
            await _seed_avatar_config(session, user_id)
            profile = await _seed_hcp_profile(session, user_id)
            await session.commit()
            profile_id = profile.id

        # Create a bearer token for auth
        _, bearer = await _create_user_and_token("vl_real_api_caller")

        response = await client.post(
            f"/api/v1/voice-live/token?hcp_profile_id={profile_id}",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["voice_name"] == "zh-CN-YunxiNeural"
        assert data["avatar_character"] == "harry"
        assert data["avatar_style"] == "business"
        assert data["voice_temperature"] == 0.7
        assert data["turn_detection_type"] == "azure_semantic_vad"
        assert data["noise_suppression"] is True
        assert data["recognition_language"] == "zh-CN"
        assert data["agent_id"] == "asst_real_test_agent"
        assert data["auth_type"] == "bearer"

    async def test_token_endpoint_with_real_config_no_hcp(self, client):
        """POST /voice-live/token returns defaults when config exists, no hcp_profile_id."""
        async with TestSessionLocal() as session:
            user_id = await _seed_user(session, "vl_real_defaults_user")
            await _seed_master_config(session, user_id)
            await _seed_voice_live_config(session, user_id)
            await session.commit()

        _, bearer = await _create_user_and_token("vl_real_defaults_caller")

        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {bearer}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert data["turn_detection_type"] == "server_vad"
        assert data["noise_suppression"] is False
