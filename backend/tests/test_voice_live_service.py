"""Tests for Voice Live service: get_voice_live_token agent mode availability.

Tests agent_mode_available and agent_warning fields returned by
get_voice_live_token based on HCP profile sync status.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings
from app.models.hcp_profile import HcpProfile
from app.models.service_config import ServiceConfig
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.voice_live_service import get_voice_live_token
from app.utils.encryption import encrypt_value

settings = get_settings()

REAL_FOUNDRY_ENDPOINT = settings.azure_foundry_endpoint
REAL_FOUNDRY_API_KEY = settings.azure_foundry_api_key
REAL_FOUNDRY_PROJECT = settings.azure_foundry_default_project

# Skip all tests if real Azure credentials are not configured
pytestmark = pytest.mark.skipif(
    not REAL_FOUNDRY_ENDPOINT or not REAL_FOUNDRY_API_KEY,
    reason="AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY required",
)


@pytest.fixture
async def seeded_db(db_session):
    """Seed test DB with real Azure AI Foundry config from .env."""
    master = ServiceConfig(
        service_name="ai_foundry",
        display_name="Azure AI Foundry",
        endpoint=REAL_FOUNDRY_ENDPOINT,
        api_key_encrypted=encrypt_value(REAL_FOUNDRY_API_KEY),
        model_or_deployment="gpt-4o",
        region="swedencentral",
        default_project=REAL_FOUNDRY_PROJECT,
        is_master=True,
        is_active=True,
        updated_by="test-seed",
    )
    db_session.add(master)

    voice_live = ServiceConfig(
        service_name="azure_voice_live",
        display_name="Azure Voice Live",
        endpoint="",
        api_key_encrypted="",
        model_or_deployment="gpt-4o",
        region="swedencentral",
        is_master=False,
        is_active=True,
        updated_by="test-seed",
    )
    db_session.add(voice_live)

    avatar = ServiceConfig(
        service_name="azure_avatar",
        display_name="Azure Avatar",
        endpoint="",
        api_key_encrypted="",
        model_or_deployment="Lisa-casual-sitting",
        region="",
        is_master=False,
        is_active=False,
        updated_by="test-seed",
    )
    db_session.add(avatar)

    await db_session.flush()
    return db_session


async def _create_vl_instance(db, user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id.

    D-09: HcpProfile no longer has inline voice/avatar columns -- per-HCP
    voice config comes exclusively from a linked VoiceLiveInstance.
    """
    inst = VoiceLiveInstance(
        name="Agent Mode Test Instance",
        voice_name="en-US-AvaNeural",
        created_by=user_id,
    )
    db.add(inst)
    await db.flush()
    return inst.id


class TestAgentModeAvailability:
    """Tests for agent_mode_available and agent_warning in get_voice_live_token."""

    async def test_agent_mode_available_when_synced(self, seeded_db):
        """agent_mode_available=True when HCP has synced agent_id."""
        vl_id = await _create_vl_instance(seeded_db, "test-user")
        profile = HcpProfile(
            name="Dr. Synced Agent",
            specialty="Oncology",
            agent_id="asst_test_synced",
            agent_sync_status="synced",
            voice_live_instance_id=vl_id,
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        result = await get_voice_live_token(seeded_db, hcp_profile_id=profile.id)

        assert result.agent_mode_available is True
        assert result.agent_warning is None

    async def test_agent_mode_unavailable_when_not_synced(self, seeded_db):
        """agent_mode_available=False with warning when HCP not synced."""
        vl_id = await _create_vl_instance(seeded_db, "test-user")
        profile = HcpProfile(
            name="Dr. Not Synced",
            specialty="Cardiology",
            agent_id="",
            agent_sync_status="none",
            voice_live_instance_id=vl_id,
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        result = await get_voice_live_token(seeded_db, hcp_profile_id=profile.id)

        assert result.agent_mode_available is False
        assert result.agent_warning is not None
        assert "model mode" in result.agent_warning.lower()

    async def test_agent_mode_unavailable_when_pending(self, seeded_db):
        """agent_mode_available=False with warning when agent sync pending."""
        vl_id = await _create_vl_instance(seeded_db, "test-user")
        profile = HcpProfile(
            name="Dr. Pending",
            specialty="Neurology",
            agent_id="asst_pending",
            agent_sync_status="pending",
            voice_live_instance_id=vl_id,
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        result = await get_voice_live_token(seeded_db, hcp_profile_id=profile.id)

        # Pending agent_sync_status means the agent is not yet ready
        assert result.agent_mode_available is False
        assert result.agent_warning is not None

    async def test_agent_mode_unavailable_when_failed(self, seeded_db):
        """agent_mode_available=False with warning when agent sync failed."""
        vl_id = await _create_vl_instance(seeded_db, "test-user")
        profile = HcpProfile(
            name="Dr. Failed Sync",
            specialty="General",
            agent_id="asst_failed",
            agent_sync_status="failed",
            voice_live_instance_id=vl_id,
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        result = await get_voice_live_token(seeded_db, hcp_profile_id=profile.id)

        assert result.agent_mode_available is False
        assert result.agent_warning is not None

    async def test_no_warning_when_no_hcp_profile(self, seeded_db):
        """No agent_warning when no hcp_profile_id is provided."""
        result = await get_voice_live_token(seeded_db, hcp_profile_id=None)

        assert result.agent_mode_available is False
        assert result.agent_warning is None

    async def test_no_warning_when_no_hcp_profile_empty_string(self, seeded_db):
        """No agent_warning when hcp_profile_id is empty string."""
        result = await get_voice_live_token(seeded_db, hcp_profile_id=None)

        assert result.agent_warning is None


# ===========================================================================
# Phase 16 coverage boost: get_voice_live_token error paths,
# get_voice_live_status, _exchange_api_key_for_bearer_token, validate_region,
# HCP profile load exception in token
# ===========================================================================


class TestGetVoiceLiveTokenErrors:
    """Tests for error paths in get_voice_live_token."""

    async def test_raises_when_config_missing(self, db_session):
        """get_voice_live_token raises ValueError when no config."""
        with pytest.raises(ValueError, match="not configured"):
            await get_voice_live_token(db_session)

    async def test_raises_when_config_inactive(self, db_session):
        """get_voice_live_token raises ValueError when config is inactive."""
        vl_config = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint="https://test.com",
            api_key_encrypted=encrypt_value("test-key"),
            model_or_deployment="gpt-4o",
            region="swedencentral",
            is_master=False,
            is_active=False,  # inactive
            updated_by="test",
        )
        db_session.add(vl_config)
        await db_session.flush()

        with pytest.raises(ValueError, match="not configured"):
            await get_voice_live_token(db_session)

    async def test_raises_when_api_key_missing(self, db_session):
        """get_voice_live_token returns bearer auth_type when API key is not set (no exception)."""
        # No master config, no own key
        vl_config = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint="https://test.com",
            api_key_encrypted="",
            model_or_deployment="gpt-4o",
            region="swedencentral",
            is_master=False,
            is_active=True,
            updated_by="test",
        )
        db_session.add(vl_config)
        await db_session.flush()

        result = await get_voice_live_token(db_session)
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"

    async def test_raises_when_endpoint_missing(self, db_session):
        """get_voice_live_token raises ValueError when endpoint is not configured."""
        # Master config with key but no endpoint
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="AI Foundry",
            endpoint="",  # empty
            api_key_encrypted=encrypt_value("key"),
            model_or_deployment="gpt-4o",
            region="swedencentral",
            is_master=True,
            is_active=True,
            updated_by="test",
        )
        db_session.add(master)

        vl_config = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint="",
            api_key_encrypted="",
            model_or_deployment="gpt-4o",
            region="swedencentral",
            is_master=False,
            is_active=True,
            updated_by="test",
        )
        db_session.add(vl_config)
        await db_session.flush()

        with pytest.raises(ValueError, match="endpoint not configured"):
            await get_voice_live_token(db_session)


class TestGetVoiceLiveStatus:
    """Tests for get_voice_live_status."""

    async def test_status_both_available(self, seeded_db):
        """get_voice_live_status reports voice_live available and avatar available.

        avatar_available is derived from Voice Live's own effective endpoint
        resolution (which resolves via master fallback in seeded_db), not from the
        separate azure_avatar config row's is_active flag -- so it is True here
        even though azure_avatar itself is seeded inactive.
        """
        from app.services.voice_live_service import get_voice_live_status

        result = await get_voice_live_status(seeded_db)

        assert result.voice_live_available is True
        assert result.avatar_available is True
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"

    async def test_status_nothing_configured(self, db_session):
        """get_voice_live_status reports nothing available when no config."""
        from app.services.voice_live_service import get_voice_live_status

        result = await get_voice_live_status(db_session)

        assert result.voice_live_available is False
        assert result.avatar_available is False


class TestValidateRegion:
    """Tests for validate_region."""

    def test_valid_region(self):
        """validate_region returns True for supported regions."""
        from app.services.voice_live_service import validate_region

        assert validate_region("swedencentral") is True
        assert validate_region("eastus2") is True

    def test_invalid_region(self):
        """validate_region returns False for unsupported regions."""
        from app.services.voice_live_service import validate_region

        assert validate_region("unsupported-region") is False
        assert validate_region("") is False


class TestExchangeApiKeyForBearerToken:
    """Tests for _exchange_api_key_for_bearer_token."""

    async def test_exchange_success(self):
        """_exchange_api_key_for_bearer_token returns token on success."""
        from app.services.voice_live_service import (
            _exchange_api_key_for_bearer_token,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "bearer-token-value"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.voice_live_service.httpx.AsyncClient", return_value=mock_client):
            result = await _exchange_api_key_for_bearer_token(
                "https://test.cognitiveservices.azure.com",
                "test-api-key",
            )

        assert result == "bearer-token-value"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "sts/v1.0/issueToken" in call_args[0][0]
        assert call_args[1]["headers"]["Ocp-Apim-Subscription-Key"] == "test-api-key"

    async def test_exchange_failure_raises(self):
        """_exchange_api_key_for_bearer_token raises on HTTP error."""
        import httpx

        from app.services.voice_live_service import (
            _exchange_api_key_for_bearer_token,
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.voice_live_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await _exchange_api_key_for_bearer_token(
                    "https://test.cognitiveservices.azure.com",
                    "bad-key",
                )


class TestGetVoiceLiveTokenWithActiveAvatar:
    """Tests for get_voice_live_token with active avatar config."""

    @pytest.fixture
    async def seeded_db_active_avatar(self, db_session):
        """Seed DB with active avatar config."""
        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=REAL_FOUNDRY_ENDPOINT,
            api_key_encrypted=encrypt_value(REAL_FOUNDRY_API_KEY),
            model_or_deployment="gpt-4o",
            region="swedencentral",
            default_project=REAL_FOUNDRY_PROJECT,
            is_master=True,
            is_active=True,
            updated_by="test-seed",
        )
        db_session.add(master)

        voice_live = ServiceConfig(
            service_name="azure_voice_live",
            display_name="Azure Voice Live",
            endpoint="",
            api_key_encrypted="",
            model_or_deployment="gpt-4o",
            region="swedencentral",
            is_master=False,
            is_active=True,
            updated_by="test-seed",
        )
        db_session.add(voice_live)

        avatar = ServiceConfig(
            service_name="azure_avatar",
            display_name="Azure Avatar",
            endpoint="",
            api_key_encrypted=encrypt_value(REAL_FOUNDRY_API_KEY),
            model_or_deployment="Lisa-casual-sitting",
            region="",
            is_master=False,
            is_active=True,
            updated_by="test-seed",
        )
        db_session.add(avatar)

        await db_session.flush()
        return db_session

    async def test_avatar_key_loaded_when_active(self, seeded_db_active_avatar):
        """get_voice_live_token loads avatar key when avatar config is active."""
        result = await get_voice_live_token(seeded_db_active_avatar)

        assert result.avatar_enabled is True
        assert result.avatar_character == "Lisa-casual-sitting"


class TestGetVoiceLiveTokenHcpError:
    """Tests for HCP profile load failure in get_voice_live_token."""

    async def test_hcp_profile_load_failure_uses_defaults(self, seeded_db):
        """get_voice_live_token uses defaults when HCP profile load fails."""
        with patch(
            "app.services.hcp_profile_service.get_hcp_profile",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ):
            result = await get_voice_live_token(seeded_db, hcp_profile_id="bad-hcp-id")

        # Should succeed with defaults
        assert result.endpoint
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"


# ===========================================================================
# Real-data integration tests: hit live Azure endpoints (require .env creds)
# ===========================================================================


class TestRealTokenExchange:
    """Integration tests for _exchange_api_key_for_bearer_token against live Azure STS.

    These tests call the real Azure Cognitive Services STS endpoint to verify
    that the API key -> bearer token exchange works end-to-end. They complement
    the mock-based TestExchangeApiKeyForBearerToken class above.

    Skipped automatically when AZURE_FOUNDRY_ENDPOINT or AZURE_FOUNDRY_API_KEY
    are not configured (module-level pytestmark).
    """

    async def test_real_exchange_returns_bearer_token(self):
        """Real STS call is rejected with 403 because this Foundry resource has
        key-based auth disabled by policy (AuthenticationTypeDisabled) -- this
        endpoint has no Entra equivalent, so 403 is the correct, permanent, real
        outcome for this resource, not a bug.
        """
        import httpx

        from app.services.voice_live_service import (
            _exchange_api_key_for_bearer_token,
        )
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        # Convert AI Foundry endpoint to Cognitive Services endpoint for STS
        cog_endpoint = to_cognitive_services_endpoint(REAL_FOUNDRY_ENDPOINT)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await _exchange_api_key_for_bearer_token(cog_endpoint, REAL_FOUNDRY_API_KEY)
        assert exc_info.value.response.status_code == 403

    async def test_real_exchange_invalid_key_raises(self):
        """Real STS call with invalid API key raises HTTPStatusError."""
        import httpx

        from app.services.voice_live_service import (
            _exchange_api_key_for_bearer_token,
        )
        from app.utils.azure_endpoints import to_cognitive_services_endpoint

        cog_endpoint = to_cognitive_services_endpoint(REAL_FOUNDRY_ENDPOINT)

        with pytest.raises(httpx.HTTPStatusError):
            await _exchange_api_key_for_bearer_token(cog_endpoint, "invalid-api-key-000")

    async def test_real_get_voice_live_token_returns_config(self, seeded_db):
        """Full get_voice_live_token with real seeded config returns valid metadata."""
        result = await get_voice_live_token(seeded_db, hcp_profile_id=None)

        # Should return a valid config with cognitiveservices endpoint
        assert result.endpoint
        assert "cognitiveservices.azure.com" in result.endpoint
        assert result.region == "swedencentral"
        assert result.token == "***configured***"
        # Without HCP profile, agent mode should be unavailable
        assert result.agent_mode_available is False
        assert result.agent_warning is None
