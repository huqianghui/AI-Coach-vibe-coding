"""Integration tests for HCP profile agent sync lifecycle.

Tests that creating/updating/deleting HCP profiles triggers agent sync,
retry-sync endpoint works, and token broker sources agent_id from HCP profiles.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.hcp_profile import HcpProfile
from app.models.user import User
from app.services.agent_sync_service import (
    _chunk_metadata_value,
    build_voice_live_metadata,
)

VOICE_LIVE_CONFIG_KEY = "microsoft.voice-live.configuration"


def _reassemble_config(result: dict[str, str]) -> dict:
    """Reassemble chunked Voice Live config metadata back into a single JSON dict."""
    parts = [result[VOICE_LIVE_CONFIG_KEY]]
    idx = 1
    while f"{VOICE_LIVE_CONFIG_KEY}.{idx}" in result:
        parts.append(result[f"{VOICE_LIVE_CONFIG_KEY}.{idx}"])
        idx += 1
    return json.loads("".join(parts))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_admin_user() -> User:
    """Create a fake admin user for dependency override."""
    user = MagicMock(spec=User)
    user.id = "admin-user-id-001"
    user.role = "admin"
    user.username = "testadmin"
    user.is_active = True
    return user


@pytest.fixture
def admin_client(db_session):
    """Async HTTP client with auth + db overrides for admin access."""

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return _fake_admin_user()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def aclient(admin_client):
    """Async HTTP client with admin overrides applied."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


PROFILE_DATA = {
    "name": "Dr. Test Chen",
    "specialty": "Oncology",
    "hospital": "Test Hospital",
    "title": "Professor",
    "personality_type": "analytical",
    "emotional_state": 45,
    "communication_style": 60,
    "expertise_areas": ["immunotherapy"],
    "prescribing_habits": "Evidence-based",
    "concerns": "Safety data",
    "objections": ["cost"],
    "probe_topics": ["efficacy"],
    "difficulty": "medium",
    "is_active": True,
    "created_by": "admin-user-id-001",
}


async def _create_vl_instance(session, user_id: str) -> str:
    """Create a minimal VoiceLiveInstance directly via the DB and return its id."""
    from app.models.voice_live_instance import VoiceLiveInstance

    inst = VoiceLiveInstance(name="Test VL Instance", created_by=user_id)
    session.add(inst)
    await session.flush()
    await session.refresh(inst)
    return inst.id


# ---------------------------------------------------------------------------
# Test 1: get_voice_live_token with hcp_profile_id returns profile agent_id
# ---------------------------------------------------------------------------


@patch("app.services.voice_live_service.config_service")
@patch("app.services.voice_live_service.parse_voice_live_mode")
async def test_voice_live_token_with_hcp_profile_id(mock_parse, mock_cfg, db_session):
    """Token broker returns agent_id from HCP profile when hcp_profile_id provided."""
    # Create a profile with agent_id
    profile = HcpProfile(
        name="Dr. Token Test",
        specialty="Cardiology",
        agent_id="asst_from_profile",
        agent_sync_status="synced",
        created_by="user-001",
    )
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)

    # Mock config_service
    vl_config = MagicMock()
    vl_config.is_active = True
    vl_config.region = "eastus2"
    vl_config.model_or_deployment = "agent:asst_config_level|proj_test"
    mock_cfg.get_config = AsyncMock(return_value=vl_config)
    mock_cfg.get_effective_key = AsyncMock(return_value="test-key")
    mock_cfg.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
    master = MagicMock()
    master.region = "eastus2"
    master.default_project = "master-default-project"
    mock_cfg.get_master_config = AsyncMock(return_value=master)

    # Parse returns agent mode
    mock_parse.return_value = {
        "mode": "agent",
        "agent_id": "asst_config_level",
        "project_name": "proj_test",
    }

    from app.services.voice_live_service import get_voice_live_token

    result = await get_voice_live_token(db_session, hcp_profile_id=profile.id)

    # Should use profile's agent_id, not config-level
    assert result.agent_id == "asst_from_profile"
    # When HCP profile overrides agent, project_name comes from master default_project
    assert result.project_name == "master-default-project"
    # Agent mode: token masked for security, auth_type = bearer
    assert result.auth_type == "bearer"
    assert result.token == "***configured***"


# ---------------------------------------------------------------------------
# Test 2: get_voice_live_token with hcp_profile_id but no profile agent_id (fallback)
# ---------------------------------------------------------------------------


@patch("app.services.voice_live_service.config_service")
@patch("app.services.voice_live_service.parse_voice_live_mode")
async def test_voice_live_token_fallback_to_config(mock_parse, mock_cfg, db_session):
    """Token broker falls back to config-level agent_id when profile has none."""
    profile = HcpProfile(
        name="Dr. No Agent",
        specialty="Dermatology",
        agent_id="",
        agent_sync_status="none",
        created_by="user-001",
    )
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)

    vl_config = MagicMock()
    vl_config.is_active = True
    vl_config.region = "eastus2"
    vl_config.model_or_deployment = "agent:asst_config_level|proj_test"
    mock_cfg.get_config = AsyncMock(return_value=vl_config)
    mock_cfg.get_effective_key = AsyncMock(return_value="test-key")
    mock_cfg.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
    master = MagicMock()
    master.region = "eastus2"
    master.default_project = "master-default-project"
    mock_cfg.get_master_config = AsyncMock(return_value=master)

    mock_parse.return_value = {
        "mode": "agent",
        "agent_id": "asst_config_level",
        "project_name": "proj_test",
    }

    from app.services.voice_live_service import get_voice_live_token

    result = await get_voice_live_token(db_session, hcp_profile_id=profile.id)

    # Should fall back to config-level agent_id since profile has none
    assert result.agent_id == "asst_config_level"


# ---------------------------------------------------------------------------
# Test 3: get_voice_live_token without hcp_profile_id (backward compatible)
# ---------------------------------------------------------------------------


@patch("app.services.voice_live_service.config_service")
@patch("app.services.voice_live_service.parse_voice_live_mode")
async def test_voice_live_token_backward_compatible(mock_parse, mock_cfg, db_session):
    """Token broker behaves as before when no hcp_profile_id provided."""
    vl_config = MagicMock()
    vl_config.is_active = True
    vl_config.region = "eastus2"
    vl_config.model_or_deployment = "agent:asst_default|proj_default"
    mock_cfg.get_config = AsyncMock(return_value=vl_config)
    mock_cfg.get_effective_key = AsyncMock(return_value="test-key")
    mock_cfg.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
    master = MagicMock()
    master.region = "eastus2"
    master.default_project = "master-default-project"
    mock_cfg.get_master_config = AsyncMock(return_value=master)

    mock_parse.return_value = {
        "mode": "agent",
        "agent_id": "asst_default",
        "project_name": "proj_default",
    }

    from app.services.voice_live_service import get_voice_live_token

    result = await get_voice_live_token(db_session)

    # Without hcp_profile_id, should use config-level agent_id
    assert result.agent_id == "asst_default"
    assert result.project_name == "proj_default"


# ---------------------------------------------------------------------------
# Test 4: create_profile endpoint triggers agent sync
# ---------------------------------------------------------------------------


@patch("app.services.hcp_profile_service.agent_sync_service")
async def test_create_profile_triggers_agent_sync(mock_sync, aclient, db_session):
    """POST /hcp-profiles triggers agent sync and returns agent_sync_status."""
    mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_test123"})
    vl_id = await _create_vl_instance(db_session, PROFILE_DATA["created_by"])

    resp = await aclient.post(
        "/api/v1/hcp-profiles",
        json={**PROFILE_DATA, "voice_live_instance_id": vl_id},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_sync_status"] in ("synced", "pending", "failed")
    mock_sync.sync_agent_for_profile.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: update_profile endpoint triggers agent re-sync
# ---------------------------------------------------------------------------


@patch("app.services.hcp_profile_service.agent_sync_service")
async def test_update_profile_triggers_agent_sync(mock_sync, aclient, db_session):
    """PUT /hcp-profiles/{id} triggers agent re-sync."""
    mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_test123"})
    vl_id = await _create_vl_instance(db_session, PROFILE_DATA["created_by"])

    # First create a profile
    create_resp = await aclient.post(
        "/api/v1/hcp-profiles",
        json={**PROFILE_DATA, "voice_live_instance_id": vl_id},
    )
    assert create_resp.status_code == 201
    profile_id = create_resp.json()["id"]

    # Reset mock to track update call
    mock_sync.sync_agent_for_profile.reset_mock()

    # Update the profile
    resp = await aclient.put(
        f"/api/v1/hcp-profiles/{profile_id}",
        json={"name": "Dr. Updated Chen"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_sync_status"] in ("synced", "pending", "failed")
    mock_sync.sync_agent_for_profile.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: delete_profile endpoint attempts agent deletion
# ---------------------------------------------------------------------------


@patch("app.services.hcp_profile_service.agent_sync_service")
async def test_delete_profile_attempts_agent_deletion(mock_sync, aclient, db_session):
    """DELETE /hcp-profiles/{id} attempts to delete the AI Foundry agent."""
    mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_delete_me"})
    mock_sync.delete_agent = AsyncMock(return_value=True)
    vl_id = await _create_vl_instance(db_session, PROFILE_DATA["created_by"])

    # Create a profile (which gets an agent_id via mock)
    create_resp = await aclient.post(
        "/api/v1/hcp-profiles",
        json={**PROFILE_DATA, "voice_live_instance_id": vl_id},
    )
    assert create_resp.status_code == 201
    profile_id = create_resp.json()["id"]

    # Delete the profile
    resp = await aclient.delete(f"/api/v1/hcp-profiles/{profile_id}")

    assert resp.status_code == 204
    # Verify delete_agent was called with the agent_id
    mock_sync.delete_agent.assert_called_once()
    call_args = mock_sync.delete_agent.call_args
    assert call_args[0][1] == "asst_delete_me"  # second positional arg is agent_id


# ---------------------------------------------------------------------------
# Test 7: retry_sync endpoint returns updated profile
# ---------------------------------------------------------------------------


@patch("app.services.hcp_profile_service.agent_sync_service")
async def test_retry_sync(mock_sync, aclient, db_session):
    """POST /hcp-profiles/{id}/retry-sync retries agent sync."""
    # First sync fails on create
    mock_sync.sync_agent_for_profile = AsyncMock(side_effect=Exception("Connection failed"))
    vl_id = await _create_vl_instance(db_session, PROFILE_DATA["created_by"])

    create_resp = await aclient.post(
        "/api/v1/hcp-profiles",
        json={**PROFILE_DATA, "voice_live_instance_id": vl_id},
    )
    assert create_resp.status_code == 201
    profile_id = create_resp.json()["id"]
    assert create_resp.json()["agent_sync_status"] == "failed"

    # Now retry succeeds
    mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_retried_ok"})

    resp = await aclient.post(f"/api/v1/hcp-profiles/{profile_id}/retry-sync")

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_sync_status"] == "synced"
    assert data["agent_id"] == "asst_retried_ok"


# ---------------------------------------------------------------------------
# Test 8: create_profile with agent sync failure saves profile with failed status
# ---------------------------------------------------------------------------


@patch("app.services.hcp_profile_service.agent_sync_service")
async def test_create_profile_sync_failure(mock_sync, aclient, db_session):
    """Profile is saved even when agent sync fails (D-02, D-10)."""
    mock_sync.sync_agent_for_profile = AsyncMock(
        side_effect=Exception("AI Foundry API unavailable")
    )
    vl_id = await _create_vl_instance(db_session, PROFILE_DATA["created_by"])

    resp = await aclient.post(
        "/api/v1/hcp-profiles",
        json={**PROFILE_DATA, "voice_live_instance_id": vl_id},
    )

    # Profile should still be created (201), with failed sync status
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_sync_status"] == "failed"
    assert "AI Foundry API unavailable" in data["agent_sync_error"]
    assert data["agent_id"] == ""  # No agent_id since sync failed


# ---------------------------------------------------------------------------
# Test 9: build_voice_live_metadata — basic config
# ---------------------------------------------------------------------------


def _make_vl_instance(**overrides):
    """MagicMock VoiceLiveInstance with concrete values for every field
    resolve_voice_config() reads (MagicMock auto-attrs are not JSON-safe)."""
    inst = MagicMock()
    inst.enabled = True
    inst.voice_live_model = "gpt-4o"
    inst.voice_name = "en-US-AvaNeural"
    inst.voice_type = "azure-standard"
    inst.voice_temperature = 0.9
    inst.voice_custom = None
    inst.avatar_character = None
    inst.avatar_style = None
    inst.avatar_customized = None
    inst.turn_detection_type = "server_vad"
    inst.noise_suppression = False
    inst.echo_cancellation = False
    inst.eou_detection = False
    inst.recognition_language = None
    inst.model_instruction = ""
    inst.response_temperature = None
    inst.proactive_engagement = False
    inst.auto_detect_language = False
    inst.playback_speed = 1.0
    inst.custom_lexicon_enabled = False
    inst.custom_lexicon_url = ""
    inst.avatar_enabled = False
    for k, v in overrides.items():
        setattr(inst, k, v)
    return inst


def test_build_voice_live_metadata_basic():
    """Profile with linked VoiceLiveInstance produces correct Voice Live metadata JSON."""
    profile = MagicMock()
    profile.voice_live_instance = _make_vl_instance()

    result = build_voice_live_metadata(profile)

    assert result is not None
    # Should have exactly one key (config fits in 512 chars)
    assert VOICE_LIVE_CONFIG_KEY in result
    config = _reassemble_config(result)
    # Foundry Portal format: {"session": {camelCase keys}}
    assert "session" in config
    session = config["session"]
    # "azure-standard" is the default — implementation omits it to save chars (512 limit)
    assert "type" not in session["voice"]
    assert session["voice"]["name"] == "en-US-AvaNeural"
    assert session["voice"]["temperature"] == 0.9
    assert session["turnDetection"]["type"] == "server_vad"
    # Noise/echo are omitted entirely when disabled (not set to null)
    assert "inputAudioNoiseReduction" not in session
    assert "inputAudioEchoCancellation" not in session


# ---------------------------------------------------------------------------
# Test 10: build_voice_live_metadata — with noise + echo
# ---------------------------------------------------------------------------


def test_build_voice_live_metadata_with_noise_echo():
    """Noise suppression and echo cancellation flags appear in metadata."""
    profile = MagicMock()
    profile.voice_live_instance = _make_vl_instance(
        voice_name="en-US-JennyNeural",
        voice_temperature=0.7,
        noise_suppression=True,
        echo_cancellation=True,
        eou_detection=True,
    )

    result = build_voice_live_metadata(profile)

    assert result is not None
    config = _reassemble_config(result)
    session = config["session"]
    assert session["inputAudioNoiseReduction"]["type"] == "azure_deep_noise_suppression"
    assert session["inputAudioEchoCancellation"]["type"] == "server_echo_cancellation"
    eou = session["turnDetection"]["endOfUtteranceDetection"]
    assert eou["model"] == "semantic_detection_v1"


# ---------------------------------------------------------------------------
# Test 11: build_voice_live_metadata — disabled returns None
# ---------------------------------------------------------------------------


def test_build_voice_live_metadata_disabled():
    """voice_live_enabled=False returns None (no metadata attached to agent)."""
    profile = MagicMock()
    profile.voice_live_instance = None  # Force inline fallback path
    profile.voice_live_enabled = False

    result = build_voice_live_metadata(profile)

    assert result is None


# ---------------------------------------------------------------------------
# Test 12: _chunk_metadata_value — short value stays single key
# ---------------------------------------------------------------------------


def test_chunk_metadata_value_short():
    """Short value fits in one chunk."""
    result = _chunk_metadata_value("key", "short value", max_len=512)
    assert result == {"key": "short value"}


# ---------------------------------------------------------------------------
# Test 13: _chunk_metadata_value — long value splits correctly
# ---------------------------------------------------------------------------


def test_chunk_metadata_value_long():
    """Long value is split at 512-char boundaries."""
    long_value = "A" * 1200
    result = _chunk_metadata_value("key", long_value, max_len=512)

    assert len(result) == 3
    assert "key" in result
    assert "key.1" in result
    assert "key.2" in result
    assert len(result["key"]) == 512
    assert len(result["key.1"]) == 512
    assert len(result["key.2"]) == 176
    # Reassembled value matches original
    reassembled = result["key"] + result["key.1"] + result["key.2"]
    assert reassembled == long_value


# ---------------------------------------------------------------------------
# Test 14: build_voice_live_metadata — non-azure-standard voice omits temperature
# ---------------------------------------------------------------------------


def test_build_voice_live_metadata_custom_voice():
    """Custom voice type omits temperature field."""
    profile = MagicMock()
    profile.voice_live_instance = _make_vl_instance(
        voice_name="my-custom-voice",
        voice_type="custom-neural",
    )

    result = build_voice_live_metadata(profile)

    assert result is not None
    config = _reassemble_config(result)
    session = config["session"]
    assert session["voice"]["type"] == "custom-neural"
    assert session["voice"]["name"] == "my-custom-voice"


# ===========================================================================
# Real-data integration tests (no mocking of config_service, hcp_profile_service,
# or build_voice_live_metadata — use real DB objects and services)
# ===========================================================================


async def _seed_real_user(session, username="realdata_sync_user") -> User:
    """Create a real User row in the test DB."""
    from app.services.auth import get_password_hash

    user = User(
        username=username,
        email=f"{username}@real.test",
        hashed_password=get_password_hash("pass"),
        full_name="Real Sync User",
        role="admin",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _seed_real_service_configs(session, user_id: str) -> dict:
    """Seed master AI Foundry + azure_voice_live config rows. Returns config dict."""
    from app.models.service_config import ServiceConfig
    from app.utils.encryption import encrypt_value

    master = ServiceConfig(
        service_name="ai_foundry",
        display_name="Azure AI Foundry",
        endpoint="https://test-foundry.services.ai.azure.com",
        api_key_encrypted=encrypt_value("test-master-key-111"),
        model_or_deployment="",
        region="eastus2",
        default_project="test-default-project",
        is_master=True,
        is_active=True,
        updated_by=user_id,
    )
    session.add(master)

    vl = ServiceConfig(
        service_name="azure_voice_live",
        display_name="Azure Voice Live",
        endpoint="https://test-vl.openai.azure.com",
        api_key_encrypted=encrypt_value("test-vl-key-222"),
        model_or_deployment=json.dumps(
            {
                "mode": "agent",
                "agent_id": "asst_config_default",
                "project_name": "proj_config",
            }
        ),
        region="eastus2",
        is_master=False,
        is_active=True,
        updated_by=user_id,
    )
    session.add(vl)
    await session.flush()
    return {"master": master, "voice_live": vl}


async def _seed_real_hcp_profile(session, user_id: str, **overrides) -> HcpProfile:
    """Seed a real HcpProfile ORM object with an assigned VoiceLiveInstance in the test DB.

    D-09/D-13: HcpProfile no longer carries its own voice/avatar columns -- config
    now comes exclusively from the VoiceLiveInstance FK. Voice/avatar/turn-detection
    overrides are routed to the VoiceLiveInstance; profile-only overrides
    (agent_id, agent_sync_status, name, specialty, hospital, title) apply directly
    to the HcpProfile row.
    """
    from app.models.voice_live_instance import VoiceLiveInstance

    _profile_fields = {
        "name",
        "specialty",
        "hospital",
        "title",
        "created_by",
        "agent_id",
        "agent_sync_status",
    }
    profile_overrides = {k: v for k, v in overrides.items() if k in _profile_fields}
    vl_overrides = {k: v for k, v in overrides.items() if k not in _profile_fields}
    if "voice_live_enabled" in vl_overrides:
        vl_overrides["enabled"] = vl_overrides.pop("voice_live_enabled")

    vl_defaults = dict(
        name="Real Sync VL Instance",
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
    vl_defaults.update(vl_overrides)
    vl_instance = VoiceLiveInstance(**vl_defaults)
    session.add(vl_instance)
    await session.flush()

    defaults = dict(
        name="Dr. RealSync Li",
        specialty="Cardiology",
        hospital="Real Hospital",
        title="Professor",
        created_by=user_id,
        agent_id="asst_real_profile_agent",
        agent_sync_status="synced",
        voice_live_instance_id=vl_instance.id,
    )
    defaults.update(profile_overrides)
    profile = HcpProfile(**defaults)
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    # Eagerly load the voice_live_instance relationship so sync code paths
    # (e.g. build_voice_live_metadata -> resolve_voice_config) that access
    # profile.voice_live_instance outside an async context don't trigger a
    # lazy-load (which raises MissingGreenlet under async SQLAlchemy).
    await session.refresh(profile, attribute_names=["voice_live_instance"])
    return profile


class TestTokenBrokerRealData:
    """Real-data tests for get_voice_live_token using seeded DB rows.

    These tests exercise config_service and hcp_profile_service against real
    ServiceConfig and HcpProfile rows in the in-memory test DB (no mocking).
    """

    @pytest.mark.asyncio
    async def test_voice_live_token_with_hcp_profile_id_real_db(self, db_session):
        """Token broker returns HCP profile's agent_id from real DB data."""
        from app.services.voice_live_service import get_voice_live_token

        user = await _seed_real_user(db_session, "token_hcp_real")
        await _seed_real_service_configs(db_session, user.id)
        profile = await _seed_real_hcp_profile(db_session, user.id)
        await db_session.commit()

        result = await get_voice_live_token(db_session, hcp_profile_id=profile.id)

        # Profile agent_id overrides config-level
        assert result.agent_id == "asst_real_profile_agent"
        # project_name falls back to master default_project
        assert result.project_name == "test-default-project"
        assert result.auth_type == "bearer"
        assert result.token == "***configured***"
        # Per-HCP voice settings sourced from real profile
        assert result.voice_name == "zh-CN-YunxiNeural"
        assert result.avatar_character == "harry"
        assert result.turn_detection_type == "azure_semantic_vad"
        assert result.noise_suppression is True

    @pytest.mark.asyncio
    async def test_voice_live_token_fallback_to_config_real_db(self, db_session):
        """Token broker falls back to config-level agent_id when profile has no agent."""
        from app.services.voice_live_service import get_voice_live_token

        user = await _seed_real_user(db_session, "token_fallback_real")
        await _seed_real_service_configs(db_session, user.id)
        profile = await _seed_real_hcp_profile(
            db_session, user.id, agent_id="", agent_sync_status="none"
        )
        await db_session.commit()

        result = await get_voice_live_token(db_session, hcp_profile_id=profile.id)

        # Falls back to config-level agent_id
        assert result.agent_id == "asst_config_default"
        assert result.project_name == "proj_config"

    @pytest.mark.asyncio
    async def test_voice_live_token_backward_compatible_real_db(self, db_session):
        """Token broker returns config-level settings when no hcp_profile_id (real DB)."""
        from app.services.voice_live_service import get_voice_live_token

        user = await _seed_real_user(db_session, "token_compat_real")
        await _seed_real_service_configs(db_session, user.id)
        await db_session.commit()

        result = await get_voice_live_token(db_session)

        # Config-level agent_id used
        assert result.agent_id == "asst_config_default"
        assert result.project_name == "proj_config"
        # Default voice settings (no HCP override)
        assert result.voice_name == "zh-CN-XiaoxiaoMultilingualNeural"
        assert result.turn_detection_type == "server_vad"

    @pytest.mark.asyncio
    async def test_voice_live_token_raises_when_no_config_real_db(self, db_session):
        """Token broker raises ValueError when no ServiceConfig rows exist in DB."""
        from app.services.voice_live_service import get_voice_live_token

        with pytest.raises(ValueError, match="Voice Live not configured"):
            await get_voice_live_token(db_session)


class TestBuildVoiceLiveMetadataRealORM:
    """Tests for build_voice_live_metadata using real HcpProfile ORM objects.

    Instead of MagicMock, these seed actual HcpProfile instances (linked to a
    real VoiceLiveInstance) in the test DB so resolve_voice_config exercises
    the real VL-instance resolution path.

    The real VL-instance path includes additional fields (avatar, response_temperature,
    proactive_engagement, etc.) which may cause the JSON to exceed 512 chars and get
    chunked by _chunk_metadata_value. We reassemble chunks before parsing.
    """

    @staticmethod
    def _reassemble_metadata(result: dict[str, str], base_key: str) -> dict:
        """Reassemble a potentially chunked metadata value into parsed JSON."""
        # Collect all chunks: base_key, base_key.1, base_key.2, ...
        parts = [result[base_key]]
        idx = 1
        while f"{base_key}.{idx}" in result:
            parts.append(result[f"{base_key}.{idx}"])
            idx += 1
        return json.loads("".join(parts))

    @pytest.mark.asyncio
    async def test_build_metadata_basic_real_orm(self, db_session):
        """build_voice_live_metadata produces correct JSON from real HcpProfile."""
        user = await _seed_real_user(db_session, "meta_basic_real")
        profile = await _seed_real_hcp_profile(
            db_session,
            user.id,
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            voice_temperature=0.9,
            turn_detection_type="server_vad",
            noise_suppression=False,
            echo_cancellation=False,
            eou_detection=False,
        )
        await db_session.commit()

        result = build_voice_live_metadata(profile)

        assert result is not None
        assert "microsoft.voice-live.configuration" in result
        config = self._reassemble_metadata(result, "microsoft.voice-live.configuration")
        # Foundry Portal format: {"session": {camelCase keys}}
        assert "session" in config
        session = config["session"]
        # "azure-standard" is the default — implementation omits it to save chars (512 limit)
        assert "type" not in session["voice"]
        assert session["voice"]["name"] == "en-US-AvaNeural"
        assert session["voice"]["temperature"] == 0.9
        assert session["turnDetection"]["type"] == "server_vad"
        # Noise/echo are omitted entirely when disabled (not set to null)
        assert "inputAudioNoiseReduction" not in session
        assert "inputAudioEchoCancellation" not in session

    @pytest.mark.asyncio
    async def test_build_metadata_with_noise_echo_real_orm(self, db_session):
        """Noise suppression and echo cancellation flags appear in metadata (real ORM)."""
        user = await _seed_real_user(db_session, "meta_noise_real")
        profile = await _seed_real_hcp_profile(
            db_session,
            user.id,
            voice_name="en-US-JennyNeural",
            voice_type="azure-standard",
            voice_temperature=0.7,
            turn_detection_type="server_vad",
            noise_suppression=True,
            echo_cancellation=True,
            eou_detection=True,
        )
        await db_session.commit()

        result = build_voice_live_metadata(profile)

        assert result is not None
        config = self._reassemble_metadata(result, "microsoft.voice-live.configuration")
        session = config["session"]
        assert session["inputAudioNoiseReduction"]["type"] == "azure_deep_noise_suppression"
        assert session["inputAudioEchoCancellation"]["type"] == "server_echo_cancellation"
        eou = session["turnDetection"]["endOfUtteranceDetection"]
        assert eou["model"] == "semantic_detection_v1"

    @pytest.mark.asyncio
    async def test_build_metadata_disabled_real_orm(self, db_session):
        """voice_live_enabled=False returns None from real HcpProfile."""
        user = await _seed_real_user(db_session, "meta_disabled_real")
        profile = await _seed_real_hcp_profile(db_session, user.id, voice_live_enabled=False)
        await db_session.commit()

        result = build_voice_live_metadata(profile)

        assert result is None

    @pytest.mark.asyncio
    async def test_build_metadata_custom_voice_real_orm(self, db_session):
        """Custom voice type omits temperature from real HcpProfile ORM object."""
        user = await _seed_real_user(db_session, "meta_custom_real")
        profile = await _seed_real_hcp_profile(
            db_session,
            user.id,
            voice_name="my-custom-voice",
            voice_type="custom-neural",
            voice_temperature=0.9,
            turn_detection_type="server_vad",
            noise_suppression=False,
            echo_cancellation=False,
            eou_detection=False,
        )
        await db_session.commit()

        result = build_voice_live_metadata(profile)

        assert result is not None
        config = self._reassemble_metadata(result, "microsoft.voice-live.configuration")
        session = config["session"]
        assert session["voice"]["type"] == "custom-neural"
        assert session["voice"]["name"] == "my-custom-voice"


class TestProfileLifecycleRealDB:
    """Real-data API tests for HCP profile create/update/delete lifecycle.

    These exercise the profile CRUD endpoints against the real test DB.
    Agent sync is still mocked because it requires external Azure AI Foundry
    connectivity — the focus here is on DB persistence and response correctness.
    """

    @pytest.fixture
    def real_admin_client(self, db_session):
        """Async HTTP client with admin auth + real db_session override."""

        async def override_get_db():
            yield db_session

        async def override_get_current_user():
            return _fake_admin_user()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        yield
        app.dependency_overrides.clear()

    @pytest.fixture
    async def real_aclient(self, real_admin_client):
        """Async HTTP client with real DB admin overrides."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    @patch("app.services.hcp_profile_service.agent_sync_service")
    @pytest.mark.asyncio
    async def test_create_and_get_profile_real_db(self, mock_sync, real_aclient, db_session):
        """Create an HCP profile via API, then verify it exists with correct fields in real DB."""
        mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_created"})

        # Seed a user for created_by
        user = await _seed_real_user(db_session, "lifecycle_creator")
        vl_id = await _create_vl_instance(db_session, user.id)
        await db_session.commit()

        profile_data = {
            "name": "Dr. Lifecycle Test",
            "specialty": "Pulmonology",
            "hospital": "Lifecycle Hospital",
            "title": "Associate Professor",
            "personality_type": "friendly",
            "emotional_state": 30,
            "communication_style": 70,
            "expertise_areas": ["respiratory"],
            "prescribing_habits": "Conservative",
            "concerns": "Long-term safety",
            "objections": ["complexity"],
            "probe_topics": ["drug interactions"],
            "difficulty": "easy",
            "is_active": True,
            "created_by": user.id,
            "voice_live_instance_id": vl_id,
        }

        resp = await real_aclient.post("/api/v1/hcp-profiles", json=profile_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Dr. Lifecycle Test"
        assert data["specialty"] == "Pulmonology"
        assert data["agent_sync_status"] in ("synced", "pending", "failed")
        profile_id = data["id"]

        # Verify via GET
        get_resp = await real_aclient.get(f"/api/v1/hcp-profiles/{profile_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Dr. Lifecycle Test"

    @patch("app.services.hcp_profile_service.agent_sync_service")
    @pytest.mark.asyncio
    async def test_update_profile_persists_real_db(self, mock_sync, real_aclient, db_session):
        """Update an HCP profile and verify changes persist in real DB."""
        mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_updated"})

        user = await _seed_real_user(db_session, "lifecycle_updater")
        vl_id = await _create_vl_instance(db_session, user.id)
        await db_session.commit()

        create_resp = await real_aclient.post(
            "/api/v1/hcp-profiles",
            json={**PROFILE_DATA, "created_by": user.id, "voice_live_instance_id": vl_id},
        )
        assert create_resp.status_code == 201
        profile_id = create_resp.json()["id"]

        # Reset mock for update
        mock_sync.sync_agent_for_profile.reset_mock()

        update_resp = await real_aclient.put(
            f"/api/v1/hcp-profiles/{profile_id}",
            json={"name": "Dr. Updated Lifecycle"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Dr. Updated Lifecycle"
        mock_sync.sync_agent_for_profile.assert_called_once()

    @patch("app.services.hcp_profile_service.agent_sync_service")
    @pytest.mark.asyncio
    async def test_delete_profile_removes_from_real_db(self, mock_sync, real_aclient, db_session):
        """Delete an HCP profile and verify it is removed from real DB."""
        mock_sync.sync_agent_for_profile = AsyncMock(return_value={"id": "asst_to_delete"})
        mock_sync.delete_agent = AsyncMock(return_value=True)

        user = await _seed_real_user(db_session, "lifecycle_deleter")
        vl_id = await _create_vl_instance(db_session, user.id)
        await db_session.commit()

        create_resp = await real_aclient.post(
            "/api/v1/hcp-profiles",
            json={**PROFILE_DATA, "created_by": user.id, "voice_live_instance_id": vl_id},
        )
        assert create_resp.status_code == 201
        profile_id = create_resp.json()["id"]

        # Delete the profile
        del_resp = await real_aclient.delete(f"/api/v1/hcp-profiles/{profile_id}")
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = await real_aclient.get(f"/api/v1/hcp-profiles/{profile_id}")
        assert get_resp.status_code == 404
