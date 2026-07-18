"""Tests for Voice Live API: token broker, connection tester, schemas, region validation,
and feature flags voice_live_enabled integration."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings
from app.models.service_config import ServiceConfig
from app.models.user import User
from app.schemas.session import SessionCreate
from app.schemas.voice_live import VoiceLiveConfigStatus, VoiceLiveTokenResponse
from app.services.auth import create_access_token, get_password_hash
from app.services.connection_tester import (
    test_azure_voice_live as _test_azure_voice_live,
)
from app.services.connection_tester import (
    test_service_connection as _test_service_connection,
)
from app.services.voice_live_service import SUPPORTED_REGIONS, validate_region
from app.utils.encryption import encrypt_value
from tests.conftest import TestSessionLocal


async def _create_user_and_token(username="vl_user") -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="VL User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


# === Schema Tests ===


class TestSessionCreateMode:
    """Tests for SessionCreate schema mode field."""

    async def test_session_create_with_mode(self):
        sc = SessionCreate(scenario_id="x", mode="voice_pipeline")
        assert sc.mode == "voice_pipeline"

    async def test_session_create_default_mode(self):
        sc = SessionCreate(scenario_id="x")
        assert sc.mode == "text"

    async def test_session_create_digital_human_mode(self):
        sc = SessionCreate(scenario_id="x", mode="digital_human_pipeline")
        assert sc.mode == "digital_human_pipeline"

    async def test_session_create_realtime_agent_mode(self):
        sc = SessionCreate(scenario_id="x", mode="voice_realtime_agent")
        assert sc.mode == "voice_realtime_agent"

    async def test_session_create_digital_human_realtime_model(self):
        sc = SessionCreate(scenario_id="x", mode="digital_human_realtime_model")
        assert sc.mode == "digital_human_realtime_model"


class TestVoiceLiveSchemas:
    """Tests for VoiceLiveTokenResponse and VoiceLiveConfigStatus schemas."""

    async def test_token_response_schema(self):
        resp = VoiceLiveTokenResponse(
            endpoint="https://example.openai.azure.com",
            token="test-key",
            region="eastus2",
            model="gpt-4o-realtime-preview",
            avatar_enabled=True,
            avatar_character="Lisa-casual-sitting",
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
        )
        assert resp.endpoint == "https://example.openai.azure.com"
        assert resp.avatar_enabled is True

    async def test_config_status_schema(self):
        status = VoiceLiveConfigStatus(
            voice_live_available=True,
            avatar_available=False,
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
            avatar_character="Lisa-casual-sitting",
        )
        assert status.voice_live_available is True
        assert status.avatar_available is False


# === Region Validation Tests ===


class TestRegionValidation:
    """Tests for validate_region and SUPPORTED_REGIONS."""

    async def test_validate_region_supported_eastus2(self):
        assert validate_region("eastus2") is True

    async def test_validate_region_supported_swedencentral(self):
        assert validate_region("swedencentral") is True

    async def test_validate_region_unsupported(self):
        assert validate_region("japanwest") is False

    async def test_validate_region_case_insensitive(self):
        assert validate_region("EastUS2") is True

    async def test_supported_regions_contains_expected(self):
        assert "eastus2" in SUPPORTED_REGIONS
        assert "swedencentral" in SUPPORTED_REGIONS
        assert "westus" in SUPPORTED_REGIONS
        assert len(SUPPORTED_REGIONS) == 20


# === Connection Tester Tests ===


class TestConnectionTester:
    """Tests for Voice Live connection tester."""

    async def test_connection_tester_voice_live_bad_region(self):
        success, message = await _test_azure_voice_live(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            region="japanwest",
        )
        assert success is False
        assert "Unsupported region" in message
        assert "japanwest" in message

    async def test_connection_tester_voice_live_bad_endpoint(self):
        success, message = await _test_azure_voice_live(
            endpoint="http://not-https.com",
            api_key="test-key",
            region="eastus2",
        )
        assert success is False
        assert "Endpoint must use HTTPS" in message

    @patch(
        "app.services.connection_tester._get_bearer_token",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_connection_tester_voice_live_no_key(self, mock_get_bearer):
        success, message = await _test_azure_voice_live(
            endpoint="https://test.openai.azure.com",
            api_key="",
            region="eastus2",
        )
        assert success is False
        assert "API key is required" in message

    @patch("app.services.connection_tester.httpx.AsyncClient")
    async def test_connection_tester_voice_live_valid(self, mock_client_cls):
        """Valid config with mocked HTTP probe returning 426 (expected for WebSocket endpoint)."""
        mock_response = MagicMock()
        mock_response.status_code = 426
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        success, message = await _test_azure_voice_live(
            endpoint="https://test.openai.azure.com",
            api_key="test-key-12345",
            region="eastus2",
        )
        assert success is True
        assert "reachable" in message.lower() or "successful" in message.lower()

    @patch("app.services.connection_tester.httpx.AsyncClient")
    async def test_connection_tester_voice_live_http_failure(self, mock_client_cls):
        """HTTP probe exception falls back to format validation."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        success, message = await _test_azure_voice_live(
            endpoint="https://test.openai.azure.com",
            api_key="test-key-12345",
            region="swedencentral",
        )
        assert success is True
        assert "valid" in message.lower()

    @patch(
        "app.services.connection_tester._get_bearer_token",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_connection_tester_dispatch_voice_live(self, mock_get_bearer):
        """test_service_connection dispatches azure_voice_live correctly."""
        success, message = await _test_service_connection(
            service_name="azure_voice_live",
            endpoint="https://test.openai.azure.com",
            api_key="",
            deployment="",
            region="eastus2",
        )
        assert success is False
        assert "API key is required" in message

    async def test_connection_tester_dispatch_unknown(self):
        success, message = await _test_service_connection(
            service_name="unknown_service",
            endpoint="",
            api_key="",
            deployment="",
            region="",
        )
        assert success is False
        assert "Unknown service" in message


# === API Endpoint Tests ===


class TestVoiceLiveAPI:
    """Tests for Voice Live API endpoints."""

    async def test_token_endpoint_unauthenticated(self, client):
        """POST /api/v1/voice-live/token returns 401 without auth header."""
        response = await client.post("/api/v1/voice-live/token")
        assert response.status_code == 401

    async def test_status_endpoint_unauthenticated(self, client):
        """GET /api/v1/voice-live/status returns 401 without auth header."""
        response = await client.get("/api/v1/voice-live/status")
        assert response.status_code == 401

    @patch("app.services.voice_live_service.config_service")
    async def test_token_endpoint_no_config(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token returns 503 when no config exists."""
        mock_config_svc.get_config = AsyncMock(return_value=None)
        mock_config_svc.get_effective_key = AsyncMock(return_value="")
        mock_config_svc.get_effective_endpoint = AsyncMock(return_value="")
        mock_config_svc.get_master_config = AsyncMock(return_value=None)

        _, token = await _create_user_and_token("vl_noconfig")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "VOICE_LIVE_NOT_CONFIGURED"

    @patch("app.services.voice_live_service.config_service")
    async def test_status_endpoint_no_config(self, mock_config_svc, client):
        """GET /api/v1/voice-live/status returns voice_live_available=False when no config."""
        mock_config_svc.get_config = AsyncMock(return_value=None)
        mock_config_svc.get_effective_key = AsyncMock(return_value="")

        _, token = await _create_user_and_token("vl_status")
        response = await client.get(
            "/api/v1/voice-live/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["voice_live_available"] is False
        assert data["avatar_available"] is False

    @patch("app.services.voice_live_service.config_service")
    async def test_token_endpoint_with_config(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token returns token when config exists."""
        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.endpoint = "https://test.openai.azure.com"
        mock_vl_config.region = "eastus2"
        mock_vl_config.model_or_deployment = "gpt-4o-realtime-preview"
        mock_vl_config.api_key_encrypted = ""

        mock_config_svc.get_config = AsyncMock(
            side_effect=lambda db, name: mock_vl_config if name == "azure_voice_live" else None
        )
        mock_config_svc.get_effective_key = AsyncMock(
            side_effect=lambda db, name: "test-api-key" if name == "azure_voice_live" else ""
        )
        mock_config_svc.get_effective_endpoint = AsyncMock(
            side_effect=lambda db, name: (
                "https://test.openai.azure.com" if name == "azure_voice_live" else ""
            )
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=None)

        _, token = await _create_user_and_token("vl_withconfig")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["endpoint"] == "https://test.openai.azure.com"
        assert data["token"] == "***configured***"
        assert data["region"] == "eastus2"
        assert data["avatar_enabled"] is True
        assert data["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert data["agent_id"] is None
        assert data["project_name"] is None


# === Security: API Key Not Exposed ===


class TestTokenBrokerSecurity:
    """Security tests: token broker must never expose raw API keys or internal prompts."""

    @patch("app.services.voice_live_service.config_service")
    async def test_token_never_contains_api_key(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token must return masked token, never the raw API key."""
        real_api_key = "sk-super-secret-azure-key-12345"
        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.endpoint = "https://test.openai.azure.com"
        mock_vl_config.region = "eastus2"
        mock_vl_config.model_or_deployment = "gpt-4o-realtime-preview"
        mock_vl_config.api_key_encrypted = ""

        mock_config_svc.get_config = AsyncMock(
            side_effect=lambda db, name: mock_vl_config if name == "azure_voice_live" else None
        )
        mock_config_svc.get_effective_key = AsyncMock(
            side_effect=lambda db, name: real_api_key if name == "azure_voice_live" else ""
        )
        mock_config_svc.get_effective_endpoint = AsyncMock(
            side_effect=lambda db, name: (
                "https://test.openai.azure.com" if name == "azure_voice_live" else ""
            )
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=None)

        _, token = await _create_user_and_token("vl_security_test")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # The raw API key must NEVER appear in the response
        raw_response = response.text
        assert real_api_key not in raw_response
        assert data["token"] == "***configured***"

    @patch("app.services.voice_live_service.config_service")
    async def test_response_does_not_contain_agent_instructions(self, mock_config_svc, client):
        """POST /api/v1/voice-live/token must not expose agent_instructions_override."""
        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.endpoint = "https://test.openai.azure.com"
        mock_vl_config.region = "eastus2"
        mock_vl_config.model_or_deployment = "gpt-4o-realtime-preview"
        mock_vl_config.api_key_encrypted = ""

        mock_config_svc.get_config = AsyncMock(
            side_effect=lambda db, name: mock_vl_config if name == "azure_voice_live" else None
        )
        mock_config_svc.get_effective_key = AsyncMock(
            side_effect=lambda db, name: "test-key" if name == "azure_voice_live" else ""
        )
        mock_config_svc.get_effective_endpoint = AsyncMock(
            side_effect=lambda db, name: (
                "https://test.openai.azure.com" if name == "azure_voice_live" else ""
            )
        )
        mock_config_svc.get_master_config = AsyncMock(return_value=None)

        _, token = await _create_user_and_token("vl_no_instructions")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "agent_instructions_override" not in data


# === Feature Flags Voice Live Tests ===


class TestFeatureFlagsVoiceLive:
    """Tests for voice_live_enabled in feature flags API."""

    async def test_feature_flags_includes_voice_live_enabled(self, client):
        """GET /api/v1/config/features includes voice_live_enabled field."""
        _, token = await _create_user_and_token("flags_vl_user")

        with patch("app.api.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.feature_avatar_enabled = False
            mock_settings.feature_voice_enabled = False
            mock_settings.feature_realtime_voice_enabled = False
            mock_settings.feature_conference_enabled = False
            mock_settings.feature_voice_live_enabled = False
            mock_settings.default_voice_mode = "text_only"
            mock_settings.region = "global"
            mock_get_settings.return_value = mock_settings

            response = await client.get(
                "/api/v1/config/features",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "voice_live_enabled" in data["features"]
        assert data["features"]["voice_live_enabled"] is False

    async def test_feature_flags_voice_live_enabled_true_when_setting_true(self, client):
        """GET /api/v1/config/features returns voice_live_enabled=True when setting is True."""
        _, token = await _create_user_and_token("flags_vl_enabled")

        with patch("app.api.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.feature_avatar_enabled = False
            mock_settings.feature_voice_enabled = False
            mock_settings.feature_realtime_voice_enabled = False
            mock_settings.feature_conference_enabled = False
            mock_settings.feature_voice_live_enabled = True
            mock_settings.default_voice_mode = "text_only"
            mock_settings.region = "global"
            mock_get_settings.return_value = mock_settings

            response = await client.get(
                "/api/v1/config/features",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["features"]["voice_live_enabled"] is True


# === Real-Data Integration Tests ===
# These tests use real Azure credentials from .env and real DB operations.
# They are skipped automatically when credentials are not available.

# Read Azure credentials from environment / settings for skip decisions
_settings = get_settings()
_AZURE_ENDPOINT = _settings.azure_foundry_endpoint or os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
_AZURE_API_KEY = _settings.azure_foundry_api_key or os.environ.get("AZURE_FOUNDRY_API_KEY", "")
_HAS_AZURE_CREDS = bool(_AZURE_ENDPOINT and _AZURE_API_KEY)

_skip_no_creds = pytest.mark.skipif(
    not _HAS_AZURE_CREDS,
    reason="AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY not set in .env",
)


async def _seed_voice_live_config(
    endpoint: str,
    api_key: str,
    region: str = "eastus2",
    model: str = "gpt-4o-realtime-preview",
    is_active: bool = True,
) -> None:
    """Seed a real azure_voice_live ServiceConfig row into the test DB."""
    async with TestSessionLocal() as session:
        config = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint=endpoint,
            api_key_encrypted=encrypt_value(api_key),
            model_or_deployment=model,
            region=region,
            is_active=is_active,
            updated_by="test-seeder",
        )
        session.add(config)
        await session.commit()


async def _seed_master_config(
    endpoint: str,
    api_key: str,
    region: str = "eastus2",
) -> None:
    """Seed the AI Foundry master config row into the test DB."""
    async with TestSessionLocal() as session:
        config = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=endpoint,
            api_key_encrypted=encrypt_value(api_key),
            region=region,
            is_master=True,
            is_active=True,
            updated_by="test-seeder",
        )
        session.add(config)
        await session.commit()


class TestRealConnectionTester:
    """Real-data tests for Voice Live connection tester against Azure endpoints."""

    @_skip_no_creds
    async def test_real_connection_tester_voice_live_valid(self):
        """Real httpx probe against Azure endpoint (no mocks).

        A valid Azure endpoint should return success (endpoint reachable),
        typically via HTTP 404/405/426 from the realtime WebSocket path.
        """
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        success, message = await _test_azure_voice_live(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
            region="eastus2",
        )
        assert success is True
        assert "reachable" in message.lower() or "successful" in message.lower()


class TestRealVoiceLiveAPI:
    """Real-data integration tests for Voice Live API endpoints.

    These tests use a real in-memory SQLite database with seeded ServiceConfig
    rows containing real Azure credentials. No mocking of config_service.
    """

    async def test_real_token_endpoint_no_config_seeded(self, client):
        """POST /api/v1/voice-live/token returns 503 when DB has no config rows.

        Uses a real empty DB — no mocking of config_service.
        """
        _, token = await _create_user_and_token("real_vl_noconfig")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "VOICE_LIVE_NOT_CONFIGURED"

    async def test_real_status_endpoint_no_config_seeded(self, client):
        """GET /api/v1/voice-live/status returns voice_live_available=False with empty DB.

        Uses a real empty DB — no mocking of config_service.
        """
        _, token = await _create_user_and_token("real_vl_status_empty")
        response = await client.get(
            "/api/v1/voice-live/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["voice_live_available"] is False
        assert data["avatar_available"] is False

    @_skip_no_creds
    async def test_real_token_endpoint_with_seeded_config(self, client):
        """POST /api/v1/voice-live/token returns 200 with seeded real credentials.

        Seeds a real azure_voice_live config row with actual Azure credentials,
        then verifies the token endpoint returns properly structured data
        with the token masked (never exposing the raw API key).
        """
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        await _seed_voice_live_config(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
            region="eastus2",
        )
        _, token = await _create_user_and_token("real_vl_withconfig")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # Verify expected structure
        assert data["endpoint"] == effective_endpoint
        assert data["token"] == "***configured***"
        assert data["region"] == "eastus2"
        assert "voice_name" in data
        assert "avatar_enabled" in data
        # Security: raw API key must NOT appear anywhere in the response
        assert _AZURE_API_KEY not in response.text

    @_skip_no_creds
    async def test_real_status_endpoint_with_seeded_config(self, client):
        """GET /api/v1/voice-live/status returns voice_live_available=True with seeded config."""
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        await _seed_voice_live_config(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
            region="eastus2",
        )
        _, token = await _create_user_and_token("real_vl_status_seeded")
        response = await client.get(
            "/api/v1/voice-live/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["voice_live_available"] is True

    @_skip_no_creds
    async def test_real_token_endpoint_with_master_fallback(self, client):
        """POST /api/v1/voice-live/token uses master AI Foundry key when per-service key is empty.

        Seeds a voice_live config row with no API key and a master config row
        with the real API key. Verifies fallback resolution works end-to-end.
        """
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        # Seed master config with real credentials
        await _seed_master_config(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
            region="eastus2",
        )
        # Seed voice_live config with no key (will fall back to master)
        async with TestSessionLocal() as session:
            config = ServiceConfig(
                service_name="azure_voice_live",
                display_name="Azure Voice Live",
                endpoint="",  # empty — falls back to master
                api_key_encrypted="",  # empty — falls back to master
                model_or_deployment="gpt-4o-realtime-preview",
                region="eastus2",
                is_active=True,
                updated_by="test-seeder",
            )
            session.add(config)
            await session.commit()

        _, token = await _create_user_and_token("real_vl_master_fallback")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "***configured***"
        assert data["endpoint"] == effective_endpoint
        # Security: raw key must not leak
        assert _AZURE_API_KEY not in response.text


class TestRealTokenBrokerSecurity:
    """Real-data security tests: seeded DB, verify API key never exposed."""

    @_skip_no_creds
    async def test_real_token_never_contains_api_key(self, client):
        """POST /api/v1/voice-live/token with real credentials never exposes the raw key."""
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        await _seed_voice_live_config(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
        )
        _, token = await _create_user_and_token("real_security_key")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        raw_response = response.text
        # The real API key must NEVER appear in any form in the response
        assert _AZURE_API_KEY not in raw_response
        data = response.json()
        assert data["token"] == "***configured***"

    @_skip_no_creds
    async def test_real_response_does_not_contain_agent_instructions(self, client):
        """POST /api/v1/voice-live/token must not expose agent_instructions_override."""
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        effective_endpoint = to_cognitive_services_endpoint(_AZURE_ENDPOINT)
        await _seed_voice_live_config(
            endpoint=effective_endpoint,
            api_key=_AZURE_API_KEY,
        )
        _, token = await _create_user_and_token("real_security_instruct")
        response = await client.post(
            "/api/v1/voice-live/token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "agent_instructions_override" not in data


class TestRealFeatureFlagsVoiceLive:
    """Real-data feature flag tests using actual get_settings() values."""

    async def test_real_feature_flags_includes_voice_live_enabled(self, client):
        """GET /api/v1/config/features includes voice_live_enabled field using real settings.

        No mocking — reads the actual feature_voice_live_enabled from .env/defaults.
        """
        _, token = await _create_user_and_token("real_flags_vl")
        response = await client.get(
            "/api/v1/config/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "voice_live_enabled" in data["features"]
        # The value should match the real settings
        expected = _settings.feature_voice_live_enabled
        assert data["features"]["voice_live_enabled"] is expected

    async def test_real_feature_flags_voice_live_type_is_bool(self, client):
        """GET /api/v1/config/features voice_live_enabled is always a boolean."""
        _, token = await _create_user_and_token("real_flags_vl_type")
        response = await client.get(
            "/api/v1/config/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["features"]["voice_live_enabled"], bool)

    async def test_real_feature_flags_all_fields_present(self, client):
        """GET /api/v1/config/features returns all expected feature flag fields."""
        _, token = await _create_user_and_token("real_flags_all")
        response = await client.get(
            "/api/v1/config/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        features = data["features"]
        expected_keys = {
            "avatar_enabled",
            "voice_enabled",
            "realtime_voice_enabled",
            "conference_enabled",
            "voice_live_enabled",
            "default_voice_mode",
            "region",
        }
        assert expected_keys.issubset(set(features.keys()))
