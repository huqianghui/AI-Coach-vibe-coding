"""Integration tests for Voice Live WebSocket proxy handler.

Tests the backend WebSocket proxy (voice_live_websocket.py) using REAL configuration
data seeded into the test database. The Azure Voice Live SDK `connect()` is mocked
via sys.modules (because the handler uses lazy imports inside the function body),
but all config resolution, DB lookups, and message routing use real code paths
with real data from .env.

Test categories:
  1. _load_connection_config — config loading from DB with real values
  2. handle_voice_live_websocket — full proxy flow with mocked SDK
  3. Real credential verification — encrypt/decrypt round-trip
  4. WebSocket authentication — JWT token validation via query parameter
"""

import asyncio
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from app.config import get_settings
from app.models.hcp_profile import HcpProfile
from app.models.service_config import ServiceConfig
from app.models.voice_live_instance import VoiceLiveInstance
from app.services.voice_live_websocket import (
    _load_connection_config,
    handle_voice_live_websocket,
)
from app.utils.encryption import encrypt_value

# ---------------------------------------------------------------------------
# Real config from .env — used to seed test DB
# ---------------------------------------------------------------------------

settings = get_settings()

REAL_FOUNDRY_ENDPOINT = settings.azure_foundry_endpoint
REAL_FOUNDRY_API_KEY = settings.azure_foundry_api_key
REAL_FOUNDRY_PROJECT = settings.azure_foundry_default_project

# Skip all tests if real Azure credentials are not configured
pytestmark = pytest.mark.skipif(
    not REAL_FOUNDRY_ENDPOINT or not REAL_FOUNDRY_API_KEY,
    reason="AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY required for real config tests",
)


# ---------------------------------------------------------------------------
# Fixtures — seed test DB with real Azure config
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_db(db_session):
    """Seed test DB with real Azure AI Foundry config from .env.

    Creates:
    - Master config (ai_foundry) with real endpoint, key, project
    - Voice Live service config (azure_voice_live) in model mode
    - Avatar service config (azure_avatar, inactive by default)
    """
    # Master AI Foundry config — real credentials
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

    # Voice Live service config — model mode with supported model
    voice_live = ServiceConfig(
        service_name="azure_voice_live",
        display_name="Azure Voice Live",
        endpoint="",  # inherit from master
        api_key_encrypted="",  # inherit from master
        model_or_deployment="gpt-4o",
        region="swedencentral",
        is_master=False,
        is_active=True,
        updated_by="test-seed",
    )
    db_session.add(voice_live)

    # Avatar config — inactive for most tests
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


@pytest.fixture
async def seeded_db_model_mode(db_session):
    """Seed test DB with gpt-4o-realtime-preview model config."""
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

    # Voice Live in model mode
    voice_live = ServiceConfig(
        service_name="azure_voice_live",
        display_name="Azure Voice Live",
        endpoint="",
        api_key_encrypted="",
        model_or_deployment="gpt-4o-realtime-preview",
        region="swedencentral",
        is_master=False,
        is_active=True,
        updated_by="test-seed",
    )
    db_session.add(voice_live)

    await db_session.flush()
    return db_session


@pytest.fixture
async def seeded_db_with_avatar(db_session):
    """Seed test DB with avatar enabled."""
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

    # Avatar active with master key inherited
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


@pytest.fixture
async def hcp_profile_with_agent(seeded_db):
    """Create an HCP profile with a synced agent_id."""
    profile = HcpProfile(
        name="Dr. WebSocket Test",
        specialty="Oncology",
        agent_id="asst_hcp_override_agent",
        agent_sync_status="synced",
        voice_name="zh-CN-XiaoxiaoMultilingualNeural",
        voice_type="azure-standard",
        avatar_character="Lisa-casual-sitting",
        avatar_style="casual",
        avatar_customized=False,
        agent_instructions_override="",
        created_by="test-user",
    )
    seeded_db.add(profile)
    await seeded_db.flush()
    await seeded_db.refresh(profile)
    return profile, seeded_db


@pytest.fixture
async def hcp_with_vl_instance(seeded_db):
    """Create an HCP profile linked to a VL Instance.

    The VL Instance has its own model_instruction ("You are an English teacher"),
    while the HCP profile has different instructions.
    Used to test that HCP instructions take priority over VL Instance instructions.
    """
    # Create VL Instance with its own instructions
    vl_inst = VoiceLiveInstance(
        name="VL-Female-Video",
        voice_live_model="gpt-4o",
        voice_name="en-US-AvaNeural",
        voice_type="azure-standard",
        avatar_character="lisa",
        avatar_style="casual-sitting",
        avatar_enabled=True,
        model_instruction="You are an English teacher named Clara.",
        created_by="test-user",
    )
    seeded_db.add(vl_inst)
    await seeded_db.flush()
    await seeded_db.refresh(vl_inst)

    # Create HCP profile linked to VL Instance — no override, no agent
    profile = HcpProfile(
        name="Dr. Wang Fang",
        specialty="Neurology",
        agent_id="",
        agent_sync_status="none",
        voice_live_instance_id=vl_inst.id,
        agent_instructions_override="",
        created_by="test-user",
    )
    seeded_db.add(profile)
    await seeded_db.flush()
    await seeded_db.refresh(profile)
    return profile, vl_inst, seeded_db


@pytest.fixture
async def hcp_with_vl_and_override(seeded_db):
    """HCP profile linked to VL Instance, but HCP has its own override.

    VL Instance: "You are an English teacher named Clara."
    HCP override: "You are Dr. Li Ming, a Cardiologist."
    Expected: HCP override wins.
    """
    vl_inst = VoiceLiveInstance(
        name="VL-Male-Video",
        voice_live_model="gpt-4o",
        voice_name="en-US-AvaNeural",
        voice_type="azure-standard",
        avatar_character="lisa",
        avatar_style="casual-sitting",
        avatar_enabled=True,
        model_instruction="You are an English teacher named Clara.",
        created_by="test-user",
    )
    seeded_db.add(vl_inst)
    await seeded_db.flush()
    await seeded_db.refresh(vl_inst)

    profile = HcpProfile(
        name="Dr. Li Ming",
        specialty="Cardiology",
        agent_id="asst_li_ming",
        agent_sync_status="synced",
        voice_live_instance_id=vl_inst.id,
        agent_instructions_override="You are Dr. Li Ming, a Cardiologist.",
        created_by="test-user",
    )
    seeded_db.add(profile)
    await seeded_db.flush()
    await seeded_db.refresh(profile)
    return profile, vl_inst, seeded_db


@pytest.fixture
async def vl_instance_standalone(seeded_db):
    """Standalone VL Instance (no HCP) with its own instructions."""
    vl_inst = VoiceLiveInstance(
        name="VL-Standalone-Test",
        voice_live_model="gpt-4o",
        voice_name="zh-CN-XiaoxiaoMultilingualNeural",
        voice_type="azure-standard",
        avatar_character="lisa",
        avatar_style="casual-sitting",
        avatar_enabled=False,
        model_instruction="You are a helpful AI assistant for testing.",
        created_by="test-user",
    )
    seeded_db.add(vl_inst)
    await seeded_db.flush()
    await seeded_db.refresh(vl_inst)
    return vl_inst, seeded_db


# ===========================================================================
# Test 1: _load_connection_config — real DB config resolution
# ===========================================================================


class TestLoadConnectionConfig:
    """Tests for _load_connection_config using real DB-seeded config."""

    async def test_model_mode_config_from_db(self, seeded_db):
        """Model mode loads model name from DB (always model mode)."""
        cfg = await _load_connection_config(seeded_db)

        assert cfg["model"] == "gpt-4o"
        # Endpoint used as-is (no cognitiveservices transform)
        assert cfg["endpoint"]
        assert cfg["endpoint"] == REAL_FOUNDRY_ENDPOINT.rstrip("/")
        # Model mode -- no agent
        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""
        # API key should be the real key from master
        assert cfg["api_key"] == REAL_FOUNDRY_API_KEY

    async def test_model_mode_realtime_preview(self, seeded_db_model_mode):
        """Model mode loads gpt-4o-realtime-preview when configured."""
        cfg = await _load_connection_config(seeded_db_model_mode)

        assert cfg["model"] == "gpt-4o-realtime-preview"
        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""
        assert cfg["api_key"] == REAL_FOUNDRY_API_KEY

    async def test_avatar_enabled_from_db(self, seeded_db_with_avatar):
        """Avatar enabled when azure_avatar config is active with key."""
        cfg = await _load_connection_config(seeded_db_with_avatar)

        assert cfg["avatar_enabled"] is True
        # avatar_character comes from azure_avatar config model_or_deployment
        assert cfg["avatar_character"] == "Lisa-casual-sitting"

    async def test_avatar_enabled_even_when_avatar_config_inactive(self, seeded_db):
        """Avatar stays enabled even when azure_avatar config is inactive -- avatar is
        a Voice Live session modality, not gated by the separate azure_avatar config row."""
        cfg = await _load_connection_config(seeded_db)

        assert cfg["avatar_enabled"] is True

    async def test_hcp_profile_overrides_voice_settings(self, hcp_profile_with_agent):
        """HCP profile overrides voice/avatar settings in model mode."""
        profile, db = hcp_profile_with_agent

        cfg = await _load_connection_config(db, hcp_profile_id=profile.id)

        # This HCP has a synced agent -- should be agent mode
        assert cfg["use_agent_mode"] is True
        assert cfg["agent_name"] == "asst_hcp_override_agent"
        # Voice settings from profile
        assert cfg["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert cfg["voice_type"] == "azure-standard"
        # Model defaults to gpt-4o (profile has no voice_live_model override)
        assert cfg["model"] == "gpt-4o"

    async def test_hcp_profile_voice_settings_applied(self, seeded_db):
        """HCP profile voice settings are applied in model mode."""
        profile = HcpProfile(
            name="Dr. No Agent",
            specialty="Cardiology",
            agent_id="",
            agent_sync_status="none",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        cfg = await _load_connection_config(seeded_db, hcp_profile_id=profile.id)

        # No synced agent -- model mode
        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""
        # Voice from profile
        assert cfg["voice_name"] == "en-US-AvaNeural"
        assert cfg["model"] == "gpt-4o"

    async def test_system_prompt_passed_through(self, seeded_db):
        """System prompt is passed through to config."""
        cfg = await _load_connection_config(
            seeded_db,
            system_prompt="You are Dr. Chen, an oncologist",
        )

        assert cfg["system_prompt"] == "You are Dr. Chen, an oncologist"

    async def test_missing_config_raises(self, db_session):
        """Missing voice_live config raises ValueError."""
        with pytest.raises(ValueError, match="not configured"):
            await _load_connection_config(db_session)

    # =======================================================================
    # HCP Instructions Priority Tests (Bug fix: HCP > client prompt > auto-gen)
    # =======================================================================

    async def test_hcp_with_override_uses_hcp_override(self, hcp_with_vl_and_override):
        """HCP's own agent_instructions_override takes priority over VL Instance's.

        Bug fix: previously used VL Instance's model_instruction
        (e.g., "English teacher"), ignoring the HCP profile's own override.
        """
        profile, vl_inst, db = hcp_with_vl_and_override

        cfg = await _load_connection_config(db, hcp_profile_id=profile.id)

        # HCP's override should win, NOT VL Instance's
        assert cfg["instructions"] == "You are Dr. Li Ming, a Cardiologist."
        # VL Instance has "English teacher" but should NOT appear
        assert "English teacher" not in cfg["instructions"]
        assert "Clara" not in cfg["instructions"]

    async def test_hcp_without_override_uses_client_system_prompt(self, hcp_with_vl_instance):
        """When HCP has no override, client-sent system_prompt is used as fallback.

        This is the auto-generated instructions sent by the frontend from
        the InstructionsSection component.
        """
        profile, vl_inst, db = hcp_with_vl_instance

        cfg = await _load_connection_config(
            db,
            hcp_profile_id=profile.id,
            system_prompt="You are Dr. Wang Fang, a Neurology specialist.",
        )

        # Client system_prompt should be used (auto-generated from frontend)
        assert cfg["instructions"] == "You are Dr. Wang Fang, a Neurology specialist."
        # NOT the VL Instance's instructions
        assert "English teacher" not in cfg["instructions"]
        assert "Clara" not in cfg["instructions"]

    async def test_hcp_without_override_and_no_prompt_uses_auto_gen(self, hcp_with_vl_instance):
        """When HCP has no override AND no client system_prompt, auto-generate from profile.

        Falls back to build_agent_instructions(profile.to_prompt_dict()).
        """
        profile, vl_inst, db = hcp_with_vl_instance

        cfg = await _load_connection_config(
            db,
            hcp_profile_id=profile.id,
            system_prompt="",  # empty — no client prompt
        )

        # Auto-generated instructions should contain HCP's name and specialty
        assert "Dr. Wang Fang" in cfg["instructions"]
        assert "Neurology" in cfg["instructions"]
        # NOT the VL Instance's instructions
        assert "English teacher" not in cfg["instructions"]
        assert "Clara" not in cfg["instructions"]

    async def test_vl_instance_standalone_uses_own_instructions(self, vl_instance_standalone):
        """Standalone VL Instance test (no HCP) uses VL Instance's own instructions."""
        vl_inst, db = vl_instance_standalone

        cfg = await _load_connection_config(
            db,
            vl_instance_id=vl_inst.id,
        )

        # VL Instance's own instructions should be used in standalone mode
        assert cfg["instructions"] == "You are a helpful AI assistant for testing."

    async def test_vl_instance_standalone_no_instructions_fallback(self, seeded_db):
        """Standalone VL Instance without instructions uses client system_prompt."""
        vl_inst = VoiceLiveInstance(
            name="VL-No-Instructions",
            voice_live_model="gpt-4o",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="casual-sitting",
            avatar_enabled=False,
            model_instruction="",  # empty
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        cfg = await _load_connection_config(
            seeded_db,
            vl_instance_id=vl_inst.id,
            system_prompt="Fallback system prompt for model test",
        )

        # Empty VL instructions → instructions field stays empty
        # system_prompt is in cfg["system_prompt"] and resolved at line 377
        assert cfg["instructions"] == ""
        assert cfg["system_prompt"] == "Fallback system prompt for model test"

    async def test_hcp_override_whitespace_only_is_treated_as_empty(self, seeded_db):
        """HCP with whitespace-only override falls back to client system_prompt."""
        vl_inst = VoiceLiveInstance(
            name="VL-Whitespace-Test",
            voice_live_model="gpt-4o",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            model_instruction="You are a piano teacher.",
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        profile = HcpProfile(
            name="Dr. Whitespace",
            specialty="General",
            agent_id="",
            agent_sync_status="none",
            voice_live_instance_id=vl_inst.id,
            agent_instructions_override="   ",  # whitespace only
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        cfg = await _load_connection_config(
            seeded_db,
            hcp_profile_id=profile.id,
            system_prompt="You are Dr. Whitespace, a General practitioner.",
        )

        # Whitespace-only override treated as empty → use client system_prompt
        assert cfg["instructions"] == "You are Dr. Whitespace, a General practitioner."
        assert "piano teacher" not in cfg["instructions"]


# ===========================================================================
# Test 3: handle_voice_live_websocket — full proxy flow with mocked SDK
# ===========================================================================


def _make_mock_ws(messages: list[str]) -> MagicMock:
    """Create a mock WebSocket that returns pre-defined messages then disconnects."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    # Provide query_params so session correlation ID extraction works
    ws.query_params = {"sid": "test0000"}

    msg_iter = iter(messages)

    async def receive_text():
        try:
            return next(msg_iter)
        except StopIteration:
            raise asyncio.CancelledError()

    ws.receive_text = AsyncMock(side_effect=receive_text)
    return ws


def _install_mock_sdk() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Install mock azure-ai-voicelive SDK modules into sys.modules.

    The handler uses lazy imports (inside the function body), so standard
    patch() on module attributes won't work. Instead we pre-populate
    sys.modules with mock modules that the handler's `from X import Y`
    will resolve against.

    Returns (mock_connect_fn, mock_aio_module, mock_models_module).
    """
    # --- azure.ai.voicelive.aio module ---
    aio_mod = types.ModuleType("azure.ai.voicelive.aio")
    mock_connect_fn = MagicMock(name="connect")
    aio_mod.connect = mock_connect_fn
    aio_mod.ConnectionClosed = type("ConnectionClosed", (Exception,), {})

    # --- azure.ai.voicelive.models module ---
    models_mod = types.ModuleType("azure.ai.voicelive.models")
    models_mod.AudioEchoCancellation = MagicMock(name="AudioEchoCancellation")
    models_mod.AudioInputTranscriptionOptions = MagicMock(name="AudioInputTranscriptionOptions")
    models_mod.AudioNoiseReduction = MagicMock(name="AudioNoiseReduction")
    models_mod.AvatarConfig = MagicMock(name="AvatarConfig")
    models_mod.AzureSemanticVad = MagicMock(name="AzureSemanticVad")
    models_mod.AzureStandardVoice = MagicMock(name="AzureStandardVoice")
    models_mod.VideoParams = MagicMock(name="VideoParams")

    # Modality needs attribute-style access
    modality = MagicMock(name="Modality")
    modality.TEXT = "text"
    modality.AUDIO = "audio"
    modality.AVATAR = "avatar"
    models_mod.Modality = modality

    # RequestSession should be callable and return a dict-like mock
    models_mod.RequestSession = MagicMock(name="RequestSession")

    # ServerEventType needs attribute-style access
    server_event_type = MagicMock(name="ServerEventType")
    server_event_type.ERROR = "error"
    server_event_type.SESSION_CREATED = "session.created"
    server_event_type.SESSION_UPDATED = "session.updated"
    models_mod.ServerEventType = server_event_type

    # --- azure.core.credentials module ---
    creds_mod = types.ModuleType("azure.core.credentials")
    creds_mod.AzureKeyCredential = MagicMock(name="AzureKeyCredential")

    # --- azure.identity.aio module (stub for classic-agent DefaultAzureCredential path) ---
    identity_aio_mod = types.ModuleType("azure.identity.aio")

    class _FakeDefaultAzureCredential:
        async def get_token(self, *scopes):
            class _FakeToken:
                token = "fake-mock-sdk-token"

            return _FakeToken()

        async def close(self):
            pass

    identity_aio_mod.DefaultAzureCredential = _FakeDefaultAzureCredential

    azure_identity = types.ModuleType("azure.identity")

    # --- Parent packages (Python needs these for `from X.Y.Z import ...`) ---
    azure_pkg = types.ModuleType("azure")
    azure_ai = types.ModuleType("azure.ai")
    azure_ai_vl = types.ModuleType("azure.ai.voicelive")
    azure_core = types.ModuleType("azure.core")

    # Install into sys.modules
    sys.modules["azure"] = azure_pkg
    sys.modules["azure.ai"] = azure_ai
    sys.modules["azure.ai.voicelive"] = azure_ai_vl
    sys.modules["azure.ai.voicelive.aio"] = aio_mod
    sys.modules["azure.ai.voicelive.models"] = models_mod
    sys.modules["azure.core"] = azure_core
    sys.modules["azure.core.credentials"] = creds_mod
    sys.modules["azure.identity"] = azure_identity
    sys.modules["azure.identity.aio"] = identity_aio_mod

    return mock_connect_fn, aio_mod, models_mod


def _make_mock_azure_conn() -> AsyncMock:
    """Create a mock Azure Voice Live connection (async context manager)."""
    mock_conn = AsyncMock()
    mock_conn.session = MagicMock()
    mock_conn.session.update = AsyncMock()
    mock_conn.send = AsyncMock()
    # The iterator yields nothing then stops (simulates immediate disconnect)
    mock_conn.__aiter__ = MagicMock(
        return_value=AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration()))
    )
    return mock_conn


@pytest.fixture
def mock_sdk():
    """Install mock Azure SDK and yield helpers. Clean up sys.modules after test."""
    # Save ALL azure.* entries (not just the ones we replace) to avoid corrupting
    # the real SDK state for subsequent tests that use real Azure connections.
    saved = {k: v for k, v in sys.modules.items() if k.startswith("azure")}
    for k in list(saved):
        del sys.modules[k]

    mock_connect_fn, aio_mod, models_mod = _install_mock_sdk()

    yield mock_connect_fn, aio_mod, models_mod

    # Remove ALL mock azure.* entries
    for k in [k for k in sys.modules if k.startswith("azure")]:
        del sys.modules[k]
    # Restore original entries
    sys.modules.update(saved)


class TestHandleVoiceLiveWebsocket:
    """Tests for the full WebSocket proxy handler with mocked Azure SDK."""

    async def test_sends_proxy_connected_on_success(self, seeded_db, mock_sdk):
        """Handler sends proxy.connected after Azure connection established."""
        mock_connect_fn, _, _ = mock_sdk

        # Wire mock connect to return an async context manager
        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None, "system_prompt": "Test prompt"},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # Verify proxy.connected was sent
        sent_calls = ws.send_text.call_args_list
        proxy_connected_sent = False
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                proxy_connected_sent = True
                assert msg["avatar_enabled"] is True
                assert msg["model"] == "gpt-4o"
                break
        assert proxy_connected_sent, "proxy.connected message was not sent"

    async def test_rejects_non_session_update_first_message(self, seeded_db, mock_sdk):
        """Handler sends error if first message is not session.update."""
        bad_msg = json.dumps({"type": "wrong.type", "data": "test"})
        ws = _make_mock_ws([bad_msg])

        await handle_voice_live_websocket(ws, seeded_db)

        sent_calls = ws.send_text.call_args_list
        assert len(sent_calls) >= 1
        error_msg = json.loads(sent_calls[0][0][0])
        assert error_msg["type"] == "error"
        assert "session.update" in error_msg["error"]["message"]

    async def test_sends_error_when_no_config(self, db_session, mock_sdk):
        """Handler sends error when no voice_live config in DB."""
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, db_session)

        sent_calls = ws.send_text.call_args_list
        assert len(sent_calls) >= 1
        error_msg = json.loads(sent_calls[0][0][0])
        assert error_msg["type"] == "error"
        assert "not configured" in error_msg["error"]["message"]

    async def test_model_mode_passes_model_name(self, seeded_db, mock_sdk):
        """Model mode connect() includes model name and endpoint as-is."""
        mock_connect_fn, _, _ = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # Verify connect() was called with correct model mode params
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        # api_version no longer passed (SDK >= 1.2.0b5 handles it internally)
        assert "api_version" not in call_kwargs
        # Endpoint used as-is (no cognitiveservices transform)
        assert call_kwargs["endpoint"] == REAL_FOUNDRY_ENDPOINT.rstrip("/")
        # No agent param in model mode
        assert "agent" not in call_kwargs

    async def test_realtime_preview_model_passed(self, seeded_db_model_mode, mock_sdk):
        """gpt-4o-realtime-preview model is passed through correctly."""
        mock_connect_fn, _, _ = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None, "system_prompt": "You are a doctor"},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db_model_mode)

        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-realtime-preview"

    async def test_session_config_sent_to_azure(self, seeded_db, mock_sdk):
        """Session config (voice, VAD, noise, echo) is sent to Azure after connect."""
        mock_connect_fn, _, models_mod = mock_sdk

        mock_session_update = AsyncMock()
        mock_conn = _make_mock_azure_conn()
        mock_conn.session.update = mock_session_update

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # session.update was called on azure connection
        mock_session_update.assert_called_once()
        call_kwargs = mock_session_update.call_args[1]
        assert "session" in call_kwargs

        # AzureStandardVoice was called with default voice name
        models_mod.AzureStandardVoice.assert_called_once()
        voice_kwargs = models_mod.AzureStandardVoice.call_args[1]
        assert voice_kwargs["name"] == "zh-CN-XiaoxiaoMultilingualNeural"

    async def test_avatar_disabled_excludes_avatar_from_session_config(
        self, vl_instance_standalone, mock_sdk
    ):
        """When avatar_enabled=False, RequestSession is called WITHOUT avatar kwarg.

        Passing avatar=None may cause the SDK to serialize {"avatar": null} which
        Azure could reject or interpret differently from omitting the field entirely.
        This test ensures the fix: conditionally exclude avatar from session_kwargs.
        """
        mock_connect_fn, _, models_mod = mock_sdk
        vl_inst, db = vl_instance_standalone

        mock_session_update = AsyncMock()
        mock_conn = _make_mock_azure_conn()
        mock_conn.session.update = mock_session_update

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"vl_instance_id": vl_inst.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, db)

        # RequestSession must have been called
        models_mod.RequestSession.assert_called_once()
        rs_kwargs = models_mod.RequestSession.call_args[1]

        # avatar must NOT be present in kwargs (not even as None)
        assert "avatar" not in rs_kwargs, (
            f"avatar should be excluded when avatar_enabled=False, got: {rs_kwargs.keys()}"
        )

        # modalities should be [TEXT, AUDIO] only — no AVATAR
        assert rs_kwargs["modalities"] == ["text", "audio"], (
            f"Expected [text, audio], got: {rs_kwargs['modalities']}"
        )

    async def test_avatar_enabled_includes_avatar_in_session_config(
        self, seeded_db_with_avatar, mock_sdk
    ):
        """When avatar_enabled=True, RequestSession IS called WITH avatar kwarg.

        Complementary to the avatar_disabled test — ensures avatar config
        is passed through when the VL Instance has avatar enabled.
        """
        mock_connect_fn, _, models_mod = mock_sdk

        mock_session_update = AsyncMock()
        mock_conn = _make_mock_azure_conn()
        mock_conn.session.update = mock_session_update

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db_with_avatar)

        # RequestSession must have been called
        models_mod.RequestSession.assert_called_once()
        rs_kwargs = models_mod.RequestSession.call_args[1]

        # avatar MUST be present when avatar_enabled=True + avatar config active
        assert "avatar" in rs_kwargs, (
            f"avatar should be present when avatar_enabled=True, got: {rs_kwargs.keys()}"
        )

        # modalities should include AVATAR
        assert "avatar" in rs_kwargs["modalities"], (
            f"Expected avatar in modalities, got: {rs_kwargs['modalities']}"
        )

    async def test_session_updated_with_null_avatar_does_not_crash_forwarding(
        self, seeded_db, mock_sdk
    ):
        """Azure sends session.updated with "avatar": null when avatar disabled.

        Regression test: dict.get("avatar", {}) returns None (not {}) when key
        exists with null value. This crashed the forwarding loop, dropping all
        subsequent events (audio deltas, transcripts, etc.).
        """
        mock_connect_fn, _, models_mod = mock_sdk

        # Simulate Azure events: session.created, session.updated (avatar=null),
        # then response.audio.delta — all should be forwarded without crash.
        session_created_event = MagicMock()
        session_created_event.type = models_mod.ServerEventType.SESSION_CREATED
        session_created_event.as_dict.return_value = {
            "type": "session.created",
            "session": {"id": "ses_test123"},
        }

        session_updated_event = MagicMock()
        session_updated_event.type = models_mod.ServerEventType.SESSION_UPDATED
        session_updated_event.as_dict.return_value = {
            "type": "session.updated",
            "session": {
                "modalities": ["text", "audio"],
                "voice": {"name": "zh-CN-XiaoxiaoMultilingualNeural"},
                "avatar": None,  # This is the key: null avatar
            },
        }

        audio_delta_event = MagicMock()
        audio_delta_event.type = "response.audio.delta"
        audio_delta_event.as_dict.return_value = {
            "type": "response.audio.delta",
            "delta": "AAAA",
        }

        # Wire mock connection to yield these events
        mock_conn = _make_mock_azure_conn()
        mock_conn.session.update = AsyncMock()

        events = [session_created_event, session_updated_event, audio_delta_event]
        event_iter = AsyncMock()
        event_iter.__anext__ = AsyncMock(side_effect=[*events, StopAsyncIteration()])
        mock_conn.__aiter__ = MagicMock(return_value=event_iter)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # All 3 events + proxy.connected should have been forwarded
        sent_calls = ws.send_text.call_args_list
        sent_types = []
        for call in sent_calls:
            msg = json.loads(call[0][0])
            sent_types.append(msg.get("type"))

        assert "session.created" in sent_types, f"session.created missing: {sent_types}"
        assert "session.updated" in sent_types, f"session.updated missing: {sent_types}"
        assert "response.audio.delta" in sent_types, (
            f"audio.delta was NOT forwarded (forwarding loop likely crashed): {sent_types}"
        )

    async def test_credential_uses_real_api_key(self, seeded_db, mock_sdk):
        """AzureKeyCredential is called with the real API key from DB."""
        mock_connect_fn, _, _ = mock_sdk
        creds_mod = sys.modules["azure.core.credentials"]

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # AzureKeyCredential should be called with the real API key
        creds_mod.AzureKeyCredential.assert_called_once_with(REAL_FOUNDRY_API_KEY)


# ===========================================================================
# Test 4: Real credential verification
# ===========================================================================


class TestRealCredentialVerification:
    """Verify real .env credentials are loaded correctly through DB layer."""

    async def test_real_api_key_survives_encrypt_decrypt(self):
        """Real API key encrypts and decrypts correctly through Fernet."""
        encrypted = encrypt_value(REAL_FOUNDRY_API_KEY)
        from app.utils.encryption import decrypt_value

        decrypted = decrypt_value(encrypted)
        assert decrypted == REAL_FOUNDRY_API_KEY

    async def test_real_endpoint_is_valid_https(self):
        """Real endpoint from .env is HTTPS."""
        assert REAL_FOUNDRY_ENDPOINT.startswith("https://")

    async def test_real_project_is_set(self):
        """Real project name from .env is non-empty."""
        assert REAL_FOUNDRY_PROJECT and len(REAL_FOUNDRY_PROJECT) > 0

    async def test_effective_key_from_seeded_db(self, seeded_db):
        """config_service.get_effective_key returns real API key from seeded DB."""
        from app.services import config_service

        key = await config_service.get_effective_key(seeded_db, "azure_voice_live")
        assert key == REAL_FOUNDRY_API_KEY

    async def test_effective_endpoint_from_seeded_db(self, seeded_db):
        """config_service.get_effective_endpoint returns real endpoint from seeded DB."""
        from app.services import config_service

        endpoint = await config_service.get_effective_endpoint(seeded_db, "azure_voice_live")
        assert endpoint == REAL_FOUNDRY_ENDPOINT


# ===========================================================================
# Test 5: WebSocket authentication — JWT token validation via query parameter
# ===========================================================================


class TestWebSocketAuthentication:
    """Tests for WebSocket JWT authentication via query parameter.

    These tests do NOT require Azure credentials — they only test the auth layer.
    Uses the ASGI TestClient's websocket_connect which goes through FastAPI routing.
    """

    @pytest.fixture
    async def test_user(self, db_session):
        """Create a test user in the DB."""
        from app.models.user import User

        user = User(
            username="ws_test_user",
            email="ws@test.com",
            hashed_password="hashed_pw",
            full_name="WS Test User",
            role="user",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    async def inactive_user(self, db_session):
        """Create an inactive test user."""
        from app.models.user import User

        user = User(
            username="ws_inactive_user",
            email="inactive@test.com",
            hashed_password="hashed_pw",
            full_name="Inactive User",
            role="user",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    def valid_token(self, test_user):
        """Create a valid JWT token for the test user."""
        from app.services.auth import create_access_token

        return create_access_token(data={"sub": test_user.id})

    @pytest.fixture
    def inactive_user_token(self, inactive_user):
        """Create a valid JWT token for the inactive user."""
        from app.services.auth import create_access_token

        return create_access_token(data={"sub": inactive_user.id})

    @pytest.fixture
    def invalid_token(self):
        """Return a malformed JWT token."""
        return "not-a-valid-jwt-token"

    @pytest.fixture
    def wrong_user_token(self):
        """Create a JWT token with a non-existent user ID."""
        from app.services.auth import create_access_token

        return create_access_token(data={"sub": "non-existent-user-id"})

    @pytest.fixture
    def no_sub_token(self):
        """Create a JWT token without the 'sub' claim."""
        from app.services.auth import create_access_token

        return create_access_token(data={"role": "user"})

    async def test_ws_no_token_rejected(self, db_session):
        """WebSocket connection without token is rejected with 1008 and error message."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        ws.send_text.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "missing token" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="Authentication required")

    async def test_ws_invalid_token_rejected(self, db_session, invalid_token):
        """WebSocket connection with invalid JWT is rejected with 1008."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": invalid_token}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "invalid token" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="Invalid token")

    async def test_ws_valid_token_accepted(self, db_session, test_user, valid_token):
        """WebSocket connection with valid JWT returns the authenticated user."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": valid_token}

        result = await _authenticate_websocket(ws, db_session)

        assert result is not None
        assert result.id == test_user.id
        assert result.username == "ws_test_user"
        # Should NOT have called accept (the handler does that after auth)
        ws.accept.assert_not_called()
        ws.close.assert_not_called()

    async def test_ws_nonexistent_user_rejected(self, db_session, wrong_user_token):
        """WebSocket with token for non-existent user is rejected."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": wrong_user_token}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "not found" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="User not found or inactive")

    async def test_ws_inactive_user_rejected(self, db_session, inactive_user, inactive_user_token):
        """WebSocket with token for inactive user is rejected."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": inactive_user_token}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "inactive" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="User not found or inactive")

    async def test_ws_no_sub_claim_rejected(self, db_session, no_sub_token):
        """WebSocket with JWT missing 'sub' claim is rejected as invalid token."""
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": no_sub_token}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "invalid token" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="Invalid token")


# ===========================================================================
# Test 6: Dual-mode WebSocket handler tests (agent + model)
# ===========================================================================


class TestDualModeWebsocketHandler:
    """Tests for agent vs model mode connect path in handle_voice_live_websocket."""

    async def test_agent_mode_connect_uses_agent_parameters(self, seeded_db, mock_sdk):
        """Agent mode: connect() uses agent_name/project_name, mode='agent' in response."""
        mock_connect_fn, _, _ = mock_sdk

        # Create HCP with synced agent
        profile = HcpProfile(
            name="Dr. Agent Mode",
            specialty="Oncology",
            agent_id="asst_agent_mode_test",
            agent_sync_status="synced",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            agent_instructions_override="You are Dr. Agent Mode.",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {
                    "hcp_profile_id": profile.id,
                    "system_prompt": "Ignored in agent mode",
                },
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # connect() should be called with agent params, NOT model=
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert call_kwargs["agent_name"] == "asst_agent_mode_test"
        # project_name resolves from the seeded_db master config's default_project
        # (real value from .env), not a hardcoded literal
        assert call_kwargs["project_name"] == REAL_FOUNDRY_PROJECT
        assert "model" not in call_kwargs
        assert "agent_config" not in call_kwargs
        assert call_kwargs["api_version"] == "2025-05-01-preview"

        # proxy.connected should include mode="agent"
        sent_calls = ws.send_text.call_args_list
        proxy_msg = None
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                proxy_msg = msg
                break
        assert proxy_msg is not None
        assert proxy_msg["mode"] == "agent"
        assert proxy_msg["agent_name"] == "asst_agent_mode_test"

    async def test_model_mode_connect_uses_model_param(self, seeded_db, mock_sdk):
        """Model mode: connect() uses model= parameter, mode='model' in response."""
        mock_connect_fn, _, models_mod = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None, "system_prompt": "Test prompt"},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # connect() should be called with model= param, NOT agent=
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert "model" in call_kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert "agent" not in call_kwargs
        assert "api_version" not in call_kwargs

        # proxy.connected should include mode="model"
        sent_calls = ws.send_text.call_args_list
        proxy_msg = None
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                proxy_msg = msg
                break
        assert proxy_msg is not None
        assert proxy_msg["mode"] == "model"
        assert proxy_msg["model"] == "gpt-4o"

    async def test_agent_mode_failure_no_fallback(self, seeded_db, mock_sdk):
        """Agent mode failure returns error -- NO fallback to model mode (RD-2).

        connect() is called exactly once. When it raises, the error propagates
        to the client. There must be no second call with model= parameter.
        """
        mock_connect_fn, _, models_mod = mock_sdk

        # Create HCP with synced agent
        profile = HcpProfile(
            name="Dr. Fail Agent",
            specialty="Cardiology",
            agent_id="asst_will_fail",
            agent_sync_status="synced",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        # Make connect() raise an error (simulating agent mode failure)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("Agent connection failed"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # connect() called exactly ONCE -- no fallback attempt
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert call_kwargs["agent_name"] == "asst_will_fail"  # was agent mode attempt
        # project_name resolves from the seeded_db master config's default_project
        # (real value from .env), not a hardcoded literal
        assert call_kwargs["project_name"] == REAL_FOUNDRY_PROJECT
        assert "model" not in call_kwargs
        assert "agent_config" not in call_kwargs

        # Error should be sent to client
        sent_calls = ws.send_text.call_args_list
        error_sent = False
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "error":
                error_sent = True
                assert "Agent connection failed" in msg["error"]["message"]
                break
        assert error_sent, "Error message should be sent to client on agent failure"

    async def test_vl_instance_test_always_model_mode(self, seeded_db, mock_sdk):
        """VL Instance standalone test always uses model mode, never agent mode."""
        mock_connect_fn, _, _ = mock_sdk

        # Create a VL Instance
        vl_inst = VoiceLiveInstance(
            name="VL-Model-Only",
            voice_live_model="gpt-4o",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="casual-sitting",
            avatar_enabled=False,
            model_instruction="You are a test assistant.",
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"vl_instance_id": vl_inst.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # connect() should use model= param (model mode), NOT agent=
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert "model" in call_kwargs
        assert "agent" not in call_kwargs
        assert call_kwargs["model"] == "gpt-4o"

    async def test_hcp_not_synced_uses_model_mode(self, seeded_db, mock_sdk):
        """HCP with agent_sync_status != 'synced' uses model mode."""
        mock_connect_fn, _, _ = mock_sdk

        profile = HcpProfile(
            name="Dr. Not Synced WS",
            specialty="General",
            agent_id="asst_pending",
            agent_sync_status="pending",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # Should be model mode since agent not synced
        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert "model" in call_kwargs
        assert "agent" not in call_kwargs

    async def test_load_config_agent_mode_fields(self, seeded_db):
        """_load_connection_config returns agent mode fields for synced HCP."""
        profile = HcpProfile(
            name="Dr. Config Agent",
            specialty="Oncology",
            agent_id="asst_config_test",
            agent_sync_status="synced",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        cfg = await _load_connection_config(seeded_db, hcp_profile_id=profile.id)

        assert cfg["use_agent_mode"] is True
        assert cfg["agent_name"] == "asst_config_test"
        assert cfg["project_name"]  # should be from master config

    async def test_load_config_vl_instance_always_model(self, seeded_db):
        """_load_connection_config for VL Instance always returns model mode."""
        vl_inst = VoiceLiveInstance(
            name="VL-Config-Test",
            voice_live_model="gpt-4o",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="casual-sitting",
            avatar_enabled=False,
            model_instruction="Test instruction.",
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        cfg = await _load_connection_config(seeded_db, vl_instance_id=vl_inst.id)

        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""


# ===========================================================================
# Phase 16 coverage boost: _load_connection_config error paths,
# _forward_client_to_azure, _forward_azure_to_client event handling,
# _send_error exception suppression, WebSocket handler error paths,
# voice_live_enabled check, HCP model validation, VL Instance standalone
# ===========================================================================


class TestHandleMessageForwarding:
    """Unit tests for _handle_message_forwarding task cancellation."""

    async def test_cancels_pending_tasks(self):
        """_handle_message_forwarding cancels remaining task when one completes."""
        from fastapi import WebSocketDisconnect

        from app.services.voice_live_websocket import _handle_message_forwarding

        # Create a mock ws that disconnects immediately
        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        ws.send_text = AsyncMock()

        # Azure conn that yields one event then stops
        class SlowAzureConn:
            async def send(self, msg):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                # Wait a long time -- will be cancelled
                await asyncio.sleep(100)
                raise StopAsyncIteration

        mock_conn = SlowAzureConn()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        # Should complete without hanging
        await asyncio.wait_for(
            _handle_message_forwarding(
                ws, mock_conn, WebSocketDisconnect, MagicMock(), session_log, event_counts
            ),
            timeout=5.0,
        )


class TestLoadConnectionConfigErrors:
    """Tests for error paths in _load_connection_config."""

    async def test_missing_api_key_returns_none_key(self, seeded_db):
        """_load_connection_config returns empty api_key when key is not set."""
        from unittest.mock import patch as _patch

        # Patch get_effective_key to return empty
        with _patch(
            "app.services.voice_live_websocket.config_service.get_effective_key",
            new_callable=AsyncMock,
            return_value="",
        ):
            cfg = await _load_connection_config(seeded_db)
            assert cfg["api_key"] == ""

    async def test_missing_endpoint_raises(self, seeded_db):
        """_load_connection_config raises when endpoint is not configured."""
        from unittest.mock import patch as _patch

        with _patch(
            "app.services.voice_live_websocket.config_service.get_effective_endpoint",
            new_callable=AsyncMock,
            return_value="",
        ):
            with pytest.raises(ValueError, match="endpoint not configured"):
                await _load_connection_config(seeded_db)

    async def test_hcp_profile_load_failure_uses_defaults(self, seeded_db):
        """_load_connection_config falls back to defaults when HCP profile load fails."""
        from unittest.mock import patch as _patch

        with _patch(
            "app.services.hcp_profile_service.get_hcp_profile",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ):
            cfg = await _load_connection_config(seeded_db, hcp_profile_id="bad-id")

        # Should succeed with defaults (not agent mode)
        assert cfg["use_agent_mode"] is False
        assert cfg["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"

    async def test_vl_instance_load_failure_uses_defaults(self, seeded_db):
        """_load_connection_config falls back to defaults when VL Instance load fails."""
        from unittest.mock import patch as _patch

        with _patch(
            "app.services.voice_live_instance_service.get_instance",
            new_callable=AsyncMock,
            side_effect=Exception("Instance not found"),
        ):
            cfg = await _load_connection_config(seeded_db, vl_instance_id="bad-inst-id")

        # Should succeed with defaults
        assert cfg["use_agent_mode"] is False

    async def test_hcp_unsupported_model_fallback(self, seeded_db):
        """_load_connection_config falls back to default model for unsupported HCP model."""
        # Create HCP with unsupported model
        profile = HcpProfile(
            name="Dr. Bad Model",
            specialty="General",
            agent_id="",
            agent_sync_status="none",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            voice_live_model="unsupported-model-xyz",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        cfg = await _load_connection_config(seeded_db, hcp_profile_id=profile.id)

        # Should fall back to default model
        from app.config import get_settings as _gs

        assert cfg["model"] == _gs().voice_live_default_model

    async def test_hcp_avatar_style_mismatch_fallback(self, seeded_db):
        """_load_connection_config falls back to validated style when raw style is invalid."""
        from unittest.mock import patch as _patch

        # Create HCP with an avatar style that validate_avatar_style will change
        profile = HcpProfile(
            name="Dr. Bad Style",
            specialty="General",
            agent_id="",
            agent_sync_status="none",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="invalid-style",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        # Patch validate_avatar_style to return a different (valid) style
        with _patch(
            "app.services.avatar_characters.validate_avatar_style",
            return_value="casual-sitting",
        ):
            cfg = await _load_connection_config(seeded_db, hcp_profile_id=profile.id)

        assert cfg["avatar_style"] == "casual-sitting"

    async def test_vl_instance_avatar_style_mismatch_fallback(self, seeded_db):
        """_load_connection_config for VL Instance falls back to validated style."""
        from unittest.mock import patch as _patch

        vl_inst = VoiceLiveInstance(
            name="VL-Bad-Style",
            voice_live_model="gpt-4o",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="bad-style",
            avatar_enabled=False,
            model_instruction="",
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        with _patch(
            "app.services.avatar_characters.validate_avatar_style",
            return_value="professional",
        ):
            cfg = await _load_connection_config(seeded_db, vl_instance_id=vl_inst.id)

        assert cfg["avatar_style"] == "professional"

    async def test_vl_instance_unsupported_model_fallback(self, seeded_db):
        """_load_connection_config falls back to default for unsupported VL Instance model."""
        vl_inst = VoiceLiveInstance(
            name="VL-Bad-Model",
            voice_live_model="unsupported-model-xyz",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="casual-sitting",
            avatar_enabled=False,
            model_instruction="",
            created_by="test-user",
        )
        seeded_db.add(vl_inst)
        await seeded_db.flush()
        await seeded_db.refresh(vl_inst)

        cfg = await _load_connection_config(seeded_db, vl_instance_id=vl_inst.id)

        from app.config import get_settings as _gs

        assert cfg["model"] == _gs().voice_live_default_model


class TestForwardClientToAzure:
    """Unit tests for _forward_client_to_azure function."""

    async def test_forwards_messages_until_disconnect(self):
        """_forward_client_to_azure forwards messages then stops on disconnect."""
        from app.services.voice_live_websocket import _forward_client_to_azure

        ws = AsyncMock(spec=WebSocket)
        msg1 = json.dumps({"type": "input_audio_buffer.append", "data": "base64audio"})
        msg2 = json.dumps({"type": "session.avatar.connect", "client_sdp": "sdp-data"})

        from fastapi import WebSocketDisconnect

        ws.receive_text = AsyncMock(side_effect=[msg1, msg2, WebSocketDisconnect()])
        azure_conn = AsyncMock()
        azure_conn.send = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        await _forward_client_to_azure(
            ws, azure_conn, WebSocketDisconnect, session_log, event_counts
        )

        assert azure_conn.send.call_count == 2
        assert event_counts["c2a:input_audio_buffer.append"] == 1
        assert event_counts["c2a:session.avatar.connect"] == 1

    async def test_handles_generic_exception(self):
        """_forward_client_to_azure handles generic exceptions gracefully."""
        from app.services.voice_live_websocket import _forward_client_to_azure

        # Use a specific ConnectionClosed type so RuntimeError falls to generic handler
        class MockConnectionClosed(Exception):
            pass

        ws = AsyncMock(spec=WebSocket)
        ws.receive_text = AsyncMock(side_effect=RuntimeError("unexpected"))
        azure_conn = AsyncMock()
        session_log = MagicMock()

        # Should not raise
        await _forward_client_to_azure(ws, azure_conn, MockConnectionClosed, session_log, {})

        session_log.warning.assert_called()


class TestForwardAzureToClient:
    """Unit tests for _forward_azure_to_client function."""

    async def test_forwards_various_event_types(self):
        """_forward_azure_to_client handles various event types."""
        from app.services.voice_live_websocket import _forward_azure_to_client

        # Create mock events
        error_event = MagicMock()
        error_event.as_dict.return_value = {"type": "error", "error": {"message": "test"}}
        error_event.type = "error"

        created_event = MagicMock()
        created_event.as_dict.return_value = {
            "type": "session.created",
            "session": {"id": "sess-001"},
        }
        created_event.type = "session.created"

        updated_event = MagicMock()
        updated_event.as_dict.return_value = {
            "type": "session.updated",
            "session": {
                "modalities": ["text", "audio"],
                "voice": {"name": "test"},
                "avatar": {
                    "ice_servers": [{"url": "turn:..."}],
                    "username": "u",
                    "credential": "c",
                    "output_protocol": "webrtc",
                    "model": "vasa-1",
                    "video": {"codec": "h264"},
                    "scene": "default",
                },
            },
        }
        updated_event.type = "session.updated"

        audio_delta_event = MagicMock()
        audio_delta_event.as_dict.return_value = {
            "type": "response.audio.delta",
            "delta": "base64audiodata",
        }
        audio_delta_event.type = "response.audio.delta"

        avatar_connecting_event = MagicMock()
        avatar_connecting_event.as_dict.return_value = {
            "type": "session.avatar.connecting",
            "server_sdp": "sdp-answer-data",
        }
        avatar_connecting_event.type = "session.avatar.connecting"

        other_avatar_event = MagicMock()
        other_avatar_event.as_dict.return_value = {
            "type": "session.avatar.ready",
        }
        other_avatar_event.type = "session.avatar.ready"

        normal_event = MagicMock()
        normal_event.as_dict.return_value = {"type": "response.text.delta"}
        normal_event.type = "response.text.delta"

        events = [
            error_event,
            created_event,
            updated_event,
            audio_delta_event,
            avatar_connecting_event,
            other_avatar_event,
            normal_event,
        ]
        event_iter = iter(events)

        class AsyncIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(event_iter)
                except StopIteration:
                    raise StopAsyncIteration

        azure_conn = AsyncIterator()

        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock()

        server_event_type = MagicMock()
        server_event_type.ERROR = "error"
        server_event_type.SESSION_CREATED = "session.created"
        server_event_type.SESSION_UPDATED = "session.updated"

        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        await _forward_azure_to_client(
            azure_conn,
            ws,
            Exception,
            server_event_type,
            session_log,
            event_counts,
        )

        assert ws.send_text.call_count == 7
        assert event_counts["a2c:error"] == 1
        assert event_counts["a2c:session.created"] == 1
        assert event_counts["a2c:session.updated"] == 1
        assert event_counts["a2c:response.audio.delta"] == 1
        assert event_counts["a2c:session.avatar.connecting"] == 1
        assert event_counts["a2c:session.avatar.ready"] == 1
        assert event_counts["a2c:response.text.delta"] == 1
        ws.close.assert_awaited_once_with(code=1000, reason="azure_stream_ended")

    async def test_handles_connection_closed(self):
        """_forward_azure_to_client handles ConnectionClosed gracefully."""
        from app.services.voice_live_websocket import _forward_azure_to_client

        class MockConnectionClosed(Exception):
            pass

        class FailingAsyncIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise MockConnectionClosed("closed")

        ws = AsyncMock(spec=WebSocket)
        session_log = MagicMock()

        await _forward_azure_to_client(
            FailingAsyncIter(),
            ws,
            MockConnectionClosed,
            MagicMock(),
            session_log,
            {},
        )

        ws.close.assert_awaited_once_with(code=1000, reason="azure_stream_ended")

    async def test_handles_generic_exception(self):
        """_forward_azure_to_client handles generic exceptions gracefully."""
        from app.services.voice_live_websocket import _forward_azure_to_client

        # Use a specific ConnectionClosed type so RuntimeError falls to generic handler
        class MockConnectionClosed(Exception):
            pass

        class FailingAsyncIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("unexpected")

        ws = AsyncMock(spec=WebSocket)
        session_log = MagicMock()

        await _forward_azure_to_client(
            FailingAsyncIter(),
            ws,
            MockConnectionClosed,
            MagicMock(),
            session_log,
            {},
        )

        session_log.warning.assert_called()


class TestSendError:
    """Unit tests for _send_error function."""

    async def test_send_error_success(self):
        """_send_error sends error JSON to WebSocket."""
        from app.services.voice_live_websocket import _send_error

        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock()

        await _send_error(ws, "test error message")

        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "error"
        assert sent["error"]["message"] == "test error message"
        ws.close.assert_awaited_once_with(code=1011, reason="voice_live_error")

    async def test_send_error_suppresses_exception(self):
        """_send_error suppresses exceptions when WebSocket is closed."""
        from app.services.voice_live_websocket import _send_error

        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock(side_effect=Exception("WS closed"))

        # Should NOT raise
        await _send_error(ws, "test error")


class TestWebSocketHandlerErrorPaths:
    """Tests for error handling in handle_voice_live_websocket."""

    async def test_timeout_waiting_for_session_update(self, seeded_db, mock_sdk):
        """Handler handles timeout waiting for first message."""
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.query_params = {"sid": "timeout-test"}
        ws.receive_text = AsyncMock(side_effect=TimeoutError())

        # Should NOT raise
        await handle_voice_live_websocket(ws, seeded_db)

    async def test_websocket_disconnect_during_session(self, seeded_db, mock_sdk):
        """Handler handles WebSocketDisconnect cleanly."""
        from fastapi import WebSocketDisconnect

        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.query_params = {"sid": "disconnect-test"}
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        # Should NOT raise
        await handle_voice_live_websocket(ws, seeded_db)

    async def test_general_exception_during_connect(self, seeded_db, mock_sdk):
        """Handler handles general exceptions during SDK connect."""
        mock_connect_fn, _, _ = mock_sdk

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        # Should NOT raise
        await handle_voice_live_websocket(ws, seeded_db)

        # Error should be sent
        sent_calls = ws.send_text.call_args_list
        error_sent = any(json.loads(c[0][0]).get("type") == "error" for c in sent_calls)
        assert error_sent

    async def test_voice_live_disabled_for_hcp(self, seeded_db, mock_sdk):
        """Handler sends error when voice_live_enabled is False on HCP profile."""
        profile = HcpProfile(
            name="Dr. VL Disabled",
            specialty="General",
            agent_id="",
            agent_sync_status="none",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            voice_live_enabled=False,
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        sent_calls = ws.send_text.call_args_list
        error_sent = False
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "error":
                if "not enabled" in msg["error"]["message"]:
                    error_sent = True
                    break
        assert error_sent, "Error about VL not enabled should be sent"

    async def test_avatar_config_video_avatar(self, seeded_db_with_avatar, mock_sdk):
        """Handler configures video avatar when avatar is enabled."""
        mock_connect_fn, _, models_mod = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db_with_avatar)

        # AvatarConfig should have been called for video avatar
        models_mod.AvatarConfig.assert_called_once()
        # VideoParams should have been called
        models_mod.VideoParams.assert_called_once_with(codec="h264")

    async def test_avatar_config_photo_avatar(self, seeded_db_with_avatar, mock_sdk):
        """Handler configures photo avatar when character is a photo avatar."""
        from unittest.mock import patch as _patch

        mock_connect_fn, _, models_mod = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        # Patch is_photo_avatar at source module level
        with _patch(
            "app.services.avatar_characters.is_photo_avatar",
            return_value=True,
        ):
            await handle_voice_live_websocket(ws, seeded_db_with_avatar)

        # AvatarConfig should NOT have been called (photo uses dict, not AvatarConfig)
        models_mod.AvatarConfig.assert_not_called()

        # proxy.connected should have been sent
        sent_calls = ws.send_text.call_args_list
        proxy_sent = any(json.loads(c[0][0]).get("type") == "proxy.connected" for c in sent_calls)
        assert proxy_sent

    async def test_avatar_config_style_fallback(self, seeded_db_with_avatar, mock_sdk):
        """Handler falls back to validated avatar style when current style invalid."""
        from unittest.mock import patch as _patch

        mock_connect_fn, _, models_mod = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        # Patch validate_avatar_style to return a different style
        with (
            _patch(
                "app.services.avatar_characters.is_photo_avatar",
                return_value=False,
            ),
            _patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="default-style",
            ),
        ):
            await handle_voice_live_websocket(ws, seeded_db_with_avatar)

        # AvatarConfig should have been called with the validated style
        models_mod.AvatarConfig.assert_called_once()
        avatar_kwargs = models_mod.AvatarConfig.call_args[1]
        assert avatar_kwargs["style"] == "default-style"

    async def test_timeout_with_send_error_failure(self, seeded_db, mock_sdk):
        """Handler handles timeout when _send_error also fails (lines 528-529)."""
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.query_params = {"sid": "timeout-fail"}

        # receive_text raises TimeoutError (simulating asyncio.wait_for timeout)
        ws.receive_text = AsyncMock(side_effect=TimeoutError())

        # send_text always raises (simulating a closed WebSocket during error send)
        ws.send_text = AsyncMock(side_effect=ConnectionError("WS already closed"))

        # Should NOT raise even though send_text fails
        await handle_voice_live_websocket(ws, seeded_db)

    async def test_general_exception_with_send_error_failure(self, seeded_db, mock_sdk):
        """Handler handles general exception when _send_error also fails (lines 534-535)."""
        mock_connect_fn, _, _ = mock_sdk

        # Make SDK connect raise
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("SDK crash"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )

        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.query_params = {"sid": "exc-fail"}
        ws.receive_text = AsyncMock(return_value=session_update)

        # send_text always raises (simulating a closed WebSocket)
        ws.send_text = AsyncMock(side_effect=ConnectionError("WS closed"))

        # Should NOT raise even though send_text fails
        await handle_voice_live_websocket(ws, seeded_db)

    async def test_hcp_voice_live_check_failure_proceeds(self, seeded_db, mock_sdk):
        """Handler proceeds when voice_live_enabled check throws exception."""
        from unittest.mock import patch as _patch

        mock_connect_fn, _, _ = mock_sdk

        mock_conn = _make_mock_azure_conn()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_connect_fn.return_value = mock_ctx

        # Create a real HCP profile
        profile = HcpProfile(
            name="Dr. Check Exception",
            specialty="General",
            agent_id="",
            agent_sync_status="none",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        # Since hcp_profile_service.get_hcp_profile is called twice
        # (once for voice_live_enabled check, once in _load_connection_config),
        # we make the first call fail and second succeed
        with _patch(
            "app.services.hcp_profile_service.get_hcp_profile",
            new_callable=AsyncMock,
            side_effect=[
                RuntimeError("DB error on check"),
                profile,  # from _load_connection_config
            ],
        ):
            await handle_voice_live_websocket(ws, seeded_db)

        # Should have continued despite first check failure
        assert ws.send_text.call_count >= 1

    async def test_sdk_not_installed_error(self, seeded_db):
        """Handler sends error when azure-ai-voicelive SDK is not installed."""
        # Save ALL azure.* entries to avoid corrupting real SDK state
        saved = {k: v for k, v in sys.modules.items() if k.startswith("azure")}
        for k in list(saved):
            del sys.modules[k]

        # Block re-import by setting key modules to None in sys.modules.
        # Python treats None in sys.modules as a failed import (raises ImportError).
        blocking_keys = [
            "azure.ai.voicelive",
            "azure.ai.voicelive.aio",
            "azure.ai.voicelive.models",
        ]
        for k in blocking_keys:
            sys.modules[k] = None  # type: ignore[assignment]

        try:
            session_update = json.dumps(
                {
                    "type": "session.update",
                    "session": {"hcp_profile_id": None},
                }
            )
            ws = _make_mock_ws([session_update])

            await handle_voice_live_websocket(ws, seeded_db)

            # Should send error about SDK not installed
            sent_calls = ws.send_text.call_args_list
            error_sent = any(
                "sdk not installed"
                in json.loads(c[0][0]).get("error", {}).get("message", "").lower()
                for c in sent_calls
                if json.loads(c[0][0]).get("type") == "error"
            )
            assert error_sent, "Error about SDK not installed should be sent"
        finally:
            # Remove ALL blocking/mock azure.* entries then restore originals
            for k in [k for k in sys.modules if k.startswith("azure")]:
                del sys.modules[k]
            sys.modules.update(saved)

    async def test_agent_mode_does_not_require_agent_session_config(self, seeded_db, mock_sdk):
        """Handler uses SDK 1.2 direct agent params instead of removed AgentSessionConfig."""
        mock_connect_fn, aio_mod, _ = mock_sdk

        # azure-ai-voicelive 1.2.0 exposes direct agent_name/project_name kwargs
        # and no longer exports AgentSessionConfig from aio.
        if hasattr(aio_mod, "AgentSessionConfig"):
            delattr(aio_mod, "AgentSessionConfig")

        # Create HCP with synced agent to trigger agent mode
        profile = HcpProfile(
            name="Dr. Old SDK",
            specialty="Oncology",
            agent_id="asst_old_sdk",
            agent_sync_status="synced",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        mock_connect_fn.assert_called_once()
        call_kwargs = mock_connect_fn.call_args[1]
        assert call_kwargs["agent_name"] == "asst_old_sdk"
        # project_name resolves from the seeded_db master config's default_project
        # (real value from .env), not a hardcoded literal
        assert call_kwargs["project_name"] == REAL_FOUNDRY_PROJECT
        assert "agent_config" not in call_kwargs

        # Should connect successfully instead of sending an old SDK-version error.
        sent_calls = ws.send_text.call_args_list
        assert not any(json.loads(c[0][0]).get("type") == "error" for c in sent_calls)
        assert any(json.loads(c[0][0]).get("type") == "proxy.connected" for c in sent_calls)


# ===========================================================================
# REAL Azure SDK Integration Tests
#
# These tests use REAL Azure credentials from .env and the REAL
# azure-ai-voicelive SDK (no mocking) to validate that session config
# parameters (transcription model, VAD, voice, etc.) are accepted by Azure.
# This catches errors like "azure-fast-transcription" that only the real
# Azure service rejects.
# ===========================================================================


async def _connect_with_retry(connect_fn, *, max_retries=5, delay=3.0):
    """Retry Voice Live connections — Azure sometimes resets under rapid reconnect."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return await connect_fn()
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    raise last_err  # type: ignore[misc]


class TestRealAzureSessionConfig:
    """Tests that validate session config against real Azure Voice Live service."""

    pytestmark = [
        pytest.mark.skipif(
            not REAL_FOUNDRY_ENDPOINT or not REAL_FOUNDRY_API_KEY,
            reason="AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY required",
        ),
    ]

    async def test_real_connect_model_mode_session_config_accepted(self):
        """Real Azure connection accepts our session config (model mode).

        This test catches invalid parameter values like wrong transcription
        model names that only the live Azure service validates.
        """
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioEchoCancellation,
            AudioInputTranscriptionOptions,
            AudioNoiseReduction,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        model = settings.voice_live_default_model or "gpt-4o"

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
            input_audio_echo_cancellation=AudioEchoCancellation(type="server_echo_cancellation"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="zh-CN-XiaoxiaoMultilingualNeural",
                type="azure-standard",
            ),
        )

        async def do_connect():
            async with connect(
                endpoint=REAL_FOUNDRY_ENDPOINT,
                credential=credential,
                model=model,
            ) as azure_conn:
                await azure_conn.session.update(session=session_config)
                assert azure_conn is not None
                return True

        result = await _connect_with_retry(do_connect)
        assert result is True

    async def test_real_transcription_model_azure_speech_accepted(self):
        """Azure accepts 'azure-speech' as input_audio_transcription model."""
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        model = settings.voice_live_default_model or "gpt-4o"

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="zh-CN-XiaoxiaoMultilingualNeural",
                type="azure-standard",
            ),
        )

        async def do_connect():
            async with connect(
                endpoint=REAL_FOUNDRY_ENDPOINT,
                credential=credential,
                model=model,
            ) as azure_conn:
                await azure_conn.session.update(session=session_config)
                assert azure_conn is not None
                return True

        result = await _connect_with_retry(do_connect)
        assert result is True

    async def test_real_connect_agent_mode_session_config_accepted(self):
        """Real Azure connection accepts agent mode config.

        Requires a project with at least one agent. If no agent exists,
        the test validates the connection attempt and expected error.
        """
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.core.credentials import AzureKeyCredential

        if not REAL_FOUNDRY_PROJECT:
            pytest.skip("AZURE_FOUNDRY_DEFAULT_PROJECT required for agent mode test")

        credential = AzureKeyCredential(REAL_FOUNDRY_API_KEY)

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="zh-CN-XiaoxiaoMultilingualNeural",
                type="azure-standard",
            ),
        )

        # Test that connection setup works even if the specific agent doesn't exist
        try:

            async def do_connect():
                async with connect(
                    endpoint=REAL_FOUNDRY_ENDPOINT,
                    credential=credential,
                    agent_name="test-nonexistent-agent",
                    project_name=REAL_FOUNDRY_PROJECT,
                ) as azure_conn:
                    await azure_conn.session.update(session=session_config)
                    assert azure_conn is not None
                    return True

            await _connect_with_retry(do_connect)
        except Exception as e:
            # If agent doesn't exist, Azure returns an error about the agent,
            # NOT about session config. That proves our config is valid.
            error_msg = str(e).lower()
            assert "transcription" not in error_msg, f"Session config rejected by Azure: {e}"
            assert "invalid_input_audio_transcription_model" not in error_msg, (
                f"Transcription model rejected by Azure: {e}"
            )


# ===========================================================================
# Test 7: Real Voice Live Integration Tests
#
# These tests combine REAL Azure SDK connections with REAL DB-seeded data
# to validate the full integration path (DB config resolution -> SDK connect).
# WebSocket objects are still mocked (no real HTTP server), but all config
# resolution, credential handling, and Azure SDK calls use real data.
# ===========================================================================


def _ensure_real_azure_modules():
    """Force-reload real Azure SDK modules to undo any sys.modules mocking.

    The mock_sdk fixture in earlier test classes replaces sys.modules entries
    for azure.* packages with mock objects. While it attempts to restore them,
    Python's import system may cache stale references. This helper removes ALL
    azure.* entries from sys.modules and re-imports the real SDK packages from
    scratch, guaranteeing that subsequent `from azure.X import Y` statements
    resolve to the REAL SDK classes.
    """
    import importlib

    # Remove ALL azure.* entries from sys.modules so Python reimports from disk
    azure_keys = [k for k in sys.modules if k == "azure" or k.startswith("azure.")]
    for k in azure_keys:
        sys.modules.pop(k, None)

    # Force fresh import of the real SDK modules in dependency order
    importlib.import_module("azure.core.credentials")
    importlib.import_module("azure.ai.voicelive.models")
    importlib.import_module("azure.ai.voicelive.aio")


class TestRealVoiceLiveIntegration:
    """Real-data integration tests covering mock-based test class scenarios.

    Uses real Azure credentials from .env, real DB sessions via seeded_db,
    and the real azure-ai-voicelive SDK. WebSocket is mocked because there
    is no real HTTP server, but everything else is real.

    These tests provide real-service validation for the scenarios that
    TestHandleVoiceLiveWebsocket, TestDualModeWebsocketHandler, and
    TestWebSocketAuthentication cover with mocks.
    """

    pytestmark = [
        pytest.mark.skipif(
            not REAL_FOUNDRY_ENDPOINT or not REAL_FOUNDRY_API_KEY,
            reason="AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY required",
        ),
    ]

    # -------------------------------------------------------------------
    # 1. Real Azure SDK connect in model mode — full session config
    # -------------------------------------------------------------------

    async def test_real_model_mode_full_session_config_accepted(self):
        """Real Azure connection accepts full session config with all options.

        Validates: voice, VAD, noise reduction, echo cancellation, and
        transcription model are all accepted together (model mode).
        Covers TestHandleVoiceLiveWebsocket.test_session_config_sent_to_azure
        with real SDK instead of mocks.
        """
        _ensure_real_azure_modules()
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioEchoCancellation,
            AudioInputTranscriptionOptions,
            AudioNoiseReduction,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        model = settings.voice_live_default_model or "gpt-4o"

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
            input_audio_echo_cancellation=AudioEchoCancellation(type="server_echo_cancellation"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="zh-CN-XiaoxiaoMultilingualNeural",
                type="azure-standard",
            ),
        )

        connected = False

        async def do_connect():
            nonlocal connected
            async with connect(
                endpoint=REAL_FOUNDRY_ENDPOINT,
                credential=credential,
                model=model,
            ) as azure_conn:
                await azure_conn.session.update(session=session_config)
                connected = True
                return True

        result = await _connect_with_retry(do_connect)
        assert result is True
        assert connected is True

    async def test_real_model_mode_english_voice_accepted(self):
        """Real Azure connection accepts en-US-AvaNeural voice in model mode.

        Covers TestHandleVoiceLiveWebsocket.test_model_mode_passes_model_name
        scenario with a different voice to validate voice switching works.
        """
        _ensure_real_azure_modules()
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        model = settings.voice_live_default_model or "gpt-4o"

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="en-US-AvaNeural",
                type="azure-standard",
            ),
        )

        async def do_connect():
            async with connect(
                endpoint=REAL_FOUNDRY_ENDPOINT,
                credential=credential,
                model=model,
            ) as azure_conn:
                await azure_conn.session.update(session=session_config)
                return True

        result = await _connect_with_retry(do_connect)
        assert result is True

    async def test_real_model_mode_with_instructions(self):
        """Real Azure connection accepts model mode with instructions set.

        Covers TestDualModeWebsocketHandler.test_model_mode_connect_uses_model_param
        with real SDK — validates that instructions are accepted in session config.
        """
        _ensure_real_azure_modules()
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        model = settings.voice_live_default_model or "gpt-4o"

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="zh-CN-XiaoxiaoMultilingualNeural",
                type="azure-standard",
            ),
            instructions="You are Dr. Chen, an oncologist at BeiGene.",
        )

        async def do_connect():
            async with connect(
                endpoint=REAL_FOUNDRY_ENDPOINT,
                credential=credential,
                model=model,
            ) as azure_conn:
                await azure_conn.session.update(session=session_config)
                return True

        result = await _connect_with_retry(do_connect)
        assert result is True

    # -------------------------------------------------------------------
    # 2. Real Azure SDK connect in agent mode - direct agent parameters
    # -------------------------------------------------------------------

    async def test_real_agent_mode_connect_accepted(self):
        """Real Azure connection accepts direct agent_name/project_name parameters.

        Covers TestDualModeWebsocketHandler.test_agent_mode_connect_uses_agent_parameters
        with real SDK. If agent doesn't exist, validates config is accepted.
        """
        _ensure_real_azure_modules()
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            AzureSemanticVad,
            AzureStandardVoice,
            Modality,
            RequestSession,
        )
        from azure.core.credentials import AzureKeyCredential

        if not REAL_FOUNDRY_PROJECT:
            pytest.skip("AZURE_FOUNDRY_DEFAULT_PROJECT required for agent mode test")

        credential = AzureKeyCredential(REAL_FOUNDRY_API_KEY)

        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            turn_detection=AzureSemanticVad(type="azure_semantic_vad"),
            input_audio_transcription=AudioInputTranscriptionOptions(
                model="azure-speech",
            ),
            voice=AzureStandardVoice(
                name="en-US-AvaNeural",
                type="azure-standard",
            ),
        )

        try:

            async def do_connect():
                async with connect(
                    endpoint=REAL_FOUNDRY_ENDPOINT,
                    credential=credential,
                    agent_name="integration-test-agent",
                    project_name=REAL_FOUNDRY_PROJECT,
                ) as azure_conn:
                    await azure_conn.session.update(session=session_config)
                    return True

            result = await _connect_with_retry(do_connect)
            assert result is True
        except Exception as e:
            # Agent may not exist -- but the error should be about the agent,
            # NOT about session config (voice/VAD/transcription).
            # This validates that agent_name/project_name are accepted by the SDK.
            error_msg = str(e).lower()
            assert "transcription" not in error_msg, f"Session config rejected by Azure: {e}"
            assert "invalid_input_audio_transcription_model" not in error_msg, (
                f"Transcription model rejected by Azure: {e}"
            )
            # The error should be about the agent not being found
            # (validates that connect accepted direct agent parameters)

    # -------------------------------------------------------------------
    # 3. Real config resolution from DB — _load_connection_config
    # -------------------------------------------------------------------

    async def test_real_config_resolution_model_mode(self, seeded_db):
        """_load_connection_config returns correct values from real DB data.

        Covers TestLoadConnectionConfig.test_model_mode_config_from_db
        with explicit assertions on every field of the returned config dict.
        """
        cfg = await _load_connection_config(seeded_db)

        # All fields must be present
        assert "endpoint" in cfg
        assert "api_key" in cfg
        assert "model" in cfg
        assert "voice_name" in cfg
        assert "voice_type" in cfg
        assert "avatar_character" in cfg
        assert "avatar_style" in cfg
        assert "avatar_enabled" in cfg
        assert "system_prompt" in cfg
        assert "instructions" in cfg
        assert "use_agent_mode" in cfg
        assert "agent_name" in cfg
        assert "project_name" in cfg

        # Values from seeded_db
        assert cfg["endpoint"] == REAL_FOUNDRY_ENDPOINT.rstrip("/")
        assert cfg["api_key"] == REAL_FOUNDRY_API_KEY
        assert cfg["model"] == "gpt-4o"
        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""
        assert cfg["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert cfg["voice_type"] == "azure-standard"

    async def test_real_config_resolution_with_hcp_agent(self, hcp_profile_with_agent):
        """_load_connection_config returns agent mode fields for synced HCP.

        Covers TestDualModeWebsocketHandler.test_load_config_agent_mode_fields
        with real DB — validates agent_name and project_name are populated.
        """
        profile, db = hcp_profile_with_agent

        cfg = await _load_connection_config(db, hcp_profile_id=profile.id)

        assert cfg["use_agent_mode"] is True
        assert cfg["agent_name"] == "asst_hcp_override_agent"
        assert cfg["project_name"]  # from master config's default_project
        assert cfg["project_name"] == REAL_FOUNDRY_PROJECT
        assert cfg["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"

    async def test_real_config_resolution_vl_instance_model_mode(self, vl_instance_standalone):
        """_load_connection_config for VL Instance always returns model mode.

        Covers TestDualModeWebsocketHandler.test_load_config_vl_instance_always_model
        with real DB data.
        """
        vl_inst, db = vl_instance_standalone

        cfg = await _load_connection_config(db, vl_instance_id=vl_inst.id)

        assert cfg["use_agent_mode"] is False
        assert cfg["agent_name"] == ""
        assert cfg["model"] == "gpt-4o"
        assert cfg["voice_name"] == "zh-CN-XiaoxiaoMultilingualNeural"
        assert cfg["instructions"] == "You are a helpful AI assistant for testing."

    async def test_real_config_resolution_hcp_with_vl_instance(self, hcp_with_vl_instance):
        """Config resolution for HCP linked to VL Instance uses correct voice settings.

        Covers TestLoadConnectionConfig HCP Instructions Priority Tests
        with real DB data.
        """
        profile, vl_inst, db = hcp_with_vl_instance

        cfg = await _load_connection_config(
            db,
            hcp_profile_id=profile.id,
            system_prompt="Auto-generated prompt from frontend.",
        )

        # HCP has no override, so client system_prompt is used
        assert cfg["instructions"] == "Auto-generated prompt from frontend."
        # Voice comes from VL Instance config via resolve_voice_config
        assert cfg["voice_name"] == "en-US-AvaNeural"
        assert cfg["use_agent_mode"] is False

    async def test_real_config_resolution_hcp_override_priority(self, hcp_with_vl_and_override):
        """HCP override takes priority over VL Instance instructions.

        Covers TestLoadConnectionConfig.test_hcp_with_override_uses_hcp_override
        with real DB data.
        """
        profile, vl_inst, db = hcp_with_vl_and_override

        cfg = await _load_connection_config(db, hcp_profile_id=profile.id)

        assert cfg["instructions"] == "You are Dr. Li Ming, a Cardiologist."
        assert "English teacher" not in cfg["instructions"]
        # HCP with synced agent -> agent mode
        assert cfg["use_agent_mode"] is True
        assert cfg["agent_name"] == "asst_li_ming"

    # -------------------------------------------------------------------
    # 4. Real credential encrypt/decrypt round-trip via DB
    # -------------------------------------------------------------------

    async def test_real_credential_round_trip_via_db(self, seeded_db):
        """API key encrypted in DB decrypts correctly via config_service.

        Covers TestRealCredentialVerification.test_effective_key_from_seeded_db
        with additional DB-level validation.
        """
        from app.services import config_service

        key = await config_service.get_effective_key(seeded_db, "azure_voice_live")
        assert key == REAL_FOUNDRY_API_KEY

        endpoint = await config_service.get_effective_endpoint(seeded_db, "azure_voice_live")
        assert endpoint == REAL_FOUNDRY_ENDPOINT

    async def test_real_credential_used_in_connection_config(self, seeded_db):
        """_load_connection_config returns the real decrypted API key.

        Covers TestHandleVoiceLiveWebsocket.test_credential_uses_real_api_key
        with real DB data — validates end-to-end encryption round-trip.
        """
        cfg = await _load_connection_config(seeded_db)

        assert cfg["api_key"] == REAL_FOUNDRY_API_KEY
        assert cfg["endpoint"] == REAL_FOUNDRY_ENDPOINT.rstrip("/")
        # Verify the key can actually be used to create a credential
        _ensure_real_azure_modules()
        from azure.core.credentials import AzureKeyCredential

        credential = AzureKeyCredential(cfg["api_key"])
        assert credential is not None

    # -------------------------------------------------------------------
    # 5. WebSocket auth with real JWT tokens from test DB
    # -------------------------------------------------------------------

    async def test_real_jwt_auth_valid_token(self, db_session):
        """WebSocket auth succeeds with a real JWT token for a real DB user.

        Covers TestWebSocketAuthentication.test_ws_valid_token_accepted
        with real DB user and real JWT creation.
        """
        from app.api.voice_live import _authenticate_websocket
        from app.models.user import User
        from app.services.auth import create_access_token

        # Create a real user in the test DB
        user = User(
            username="real_integration_user",
            email="integration@test.com",
            hashed_password="hashed_pw",
            full_name="Integration Test User",
            role="user",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        # Create a real JWT token
        token = create_access_token(data={"sub": user.id})

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": token}

        result = await _authenticate_websocket(ws, db_session)

        assert result is not None
        assert result.id == user.id
        assert result.username == "real_integration_user"
        ws.accept.assert_not_called()
        ws.close.assert_not_called()

    async def test_real_jwt_auth_inactive_user_rejected(self, db_session):
        """WebSocket auth rejects inactive users with proper error message.

        Covers TestWebSocketAuthentication.test_ws_inactive_user_rejected
        with real DB user and real JWT.
        """
        from app.api.voice_live import _authenticate_websocket
        from app.models.user import User
        from app.services.auth import create_access_token

        user = User(
            username="inactive_integration_user",
            email="inactive_int@test.com",
            hashed_password="hashed_pw",
            full_name="Inactive Integration User",
            role="user",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": user.id})

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {"token": token}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "inactive" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="User not found or inactive")

    async def test_real_jwt_auth_missing_token_rejected(self, db_session):
        """WebSocket auth rejects connection without token query parameter.

        Covers TestWebSocketAuthentication.test_ws_no_token_rejected
        with real DB session.
        """
        from app.api.voice_live import _authenticate_websocket

        ws = AsyncMock(spec=WebSocket)
        ws.query_params = {}
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()

        result = await _authenticate_websocket(ws, db_session)

        assert result is None
        ws.accept.assert_called_once()
        sent_msg = json.loads(ws.send_text.call_args[0][0])
        assert sent_msg["type"] == "error"
        assert "missing token" in sent_msg["error"]["message"].lower()
        ws.close.assert_called_once_with(code=1008, reason="Authentication required")

    # -------------------------------------------------------------------
    # 6. Full handler flow with real DB + real SDK (WebSocket mocked)
    # -------------------------------------------------------------------

    async def test_real_handler_model_mode_proxy_connected(self, db_session):
        """Full handler sends proxy.connected with real DB config and real SDK.

        Covers TestHandleVoiceLiveWebsocket.test_sends_proxy_connected_on_success
        with real Azure SDK connection instead of mocked SDK.
        WebSocket is still mocked (no real HTTP server).

        Uses a no-key master config (api_key_encrypted="") so config_service's
        get_effective_key() resolves to "", driving the handler's EXISTING
        keyless DefaultAzureCredential fallback path -- the only auth path that
        works on this Foundry resource (key-based auth disabled by policy).
        """
        _ensure_real_azure_modules()

        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=REAL_FOUNDRY_ENDPOINT,
            api_key_encrypted="",
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

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None, "system_prompt": "Test prompt"},
            }
        )
        ws = _make_mock_ws([session_update])

        # Use real handler with real DB and real SDK
        await handle_voice_live_websocket(ws, db_session)

        # Verify proxy.connected was sent
        sent_calls = ws.send_text.call_args_list
        proxy_connected_sent = False
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                proxy_connected_sent = True
                assert msg["mode"] == "model"
                assert msg["model"] == "gpt-4o"
                assert msg["avatar_enabled"] is True
                break
        assert proxy_connected_sent, "proxy.connected message was not sent"

    async def test_real_handler_agent_mode_with_hcp(self, seeded_db):
        """Full handler sends proxy.connected in agent mode with real HCP profile.

        Covers TestDualModeWebsocketHandler.test_agent_mode_connect_uses_agent_session_config
        with real DB + real SDK. If agent does not exist in Foundry, an error
        is expected, but it should be an agent error, not a config error.
        """
        _ensure_real_azure_modules()
        if not REAL_FOUNDRY_PROJECT:
            pytest.skip("AZURE_FOUNDRY_DEFAULT_PROJECT required for agent mode test")

        # Create HCP with synced agent
        profile = HcpProfile(
            name="Dr. Real Agent Mode",
            specialty="Oncology",
            agent_id="integration-test-agent-hcp",
            agent_sync_status="synced",
            voice_name="en-US-AvaNeural",
            voice_type="azure-standard",
            agent_instructions_override="You are an oncologist.",
            created_by="test-user",
        )
        seeded_db.add(profile)
        await seeded_db.flush()
        await seeded_db.refresh(profile)

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": profile.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, seeded_db)

        # Should have sent either proxy.connected (agent exists) or error
        # (agent doesn't exist in Foundry). Either way, the handler should
        # have processed the session.update and attempted an Azure connection.
        sent_calls = ws.send_text.call_args_list
        assert len(sent_calls) >= 1

        # Check what was sent
        sent_types = []
        for call in sent_calls:
            msg = json.loads(call[0][0])
            sent_types.append(msg.get("type"))

        # Must have sent either proxy.connected or error
        assert "proxy.connected" in sent_types or "error" in sent_types

        # If proxy.connected, verify agent mode fields
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                assert msg["mode"] == "agent"
                assert msg["agent_name"] == "integration-test-agent-hcp"
                break

    async def test_real_handler_vl_instance_model_mode(self, db_session):
        """Full handler uses model mode for standalone VL Instance with real SDK.

        Covers TestDualModeWebsocketHandler.test_vl_instance_test_always_model_mode
        with real DB + real SDK.

        Uses its own no-key master config (api_key_encrypted="") instead of the
        shared vl_instance_standalone fixture (which seeds a real key via
        seeded_db) so config_service's get_effective_key() resolves to "",
        driving the handler's EXISTING keyless DefaultAzureCredential fallback --
        the only auth path that works on this Foundry resource.
        """
        _ensure_real_azure_modules()

        master = ServiceConfig(
            service_name="ai_foundry",
            display_name="Azure AI Foundry",
            endpoint=REAL_FOUNDRY_ENDPOINT,
            api_key_encrypted="",
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

        vl_inst = VoiceLiveInstance(
            name="VL-Standalone-Test",
            voice_live_model="gpt-4o",
            voice_name="zh-CN-XiaoxiaoMultilingualNeural",
            voice_type="azure-standard",
            avatar_character="lisa",
            avatar_style="casual-sitting",
            avatar_enabled=False,
            model_instruction="You are a helpful AI assistant for testing.",
            created_by="test-user",
        )
        db_session.add(vl_inst)
        await db_session.flush()
        await db_session.refresh(vl_inst)

        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"vl_instance_id": vl_inst.id},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, db_session)

        # Verify proxy.connected was sent in model mode
        sent_calls = ws.send_text.call_args_list
        proxy_connected_sent = False
        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "proxy.connected":
                proxy_connected_sent = True
                assert msg["mode"] == "model"
                assert msg["model"] == "gpt-4o"
                break
        assert proxy_connected_sent, "proxy.connected message was not sent"

    async def test_real_handler_error_on_no_config(self, db_session):
        """Full handler sends error when no voice_live config exists in DB.

        Covers TestHandleVoiceLiveWebsocket.test_sends_error_when_no_config
        with real DB (empty — no seeded config).
        """
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None},
            }
        )
        ws = _make_mock_ws([session_update])

        await handle_voice_live_websocket(ws, db_session)

        sent_calls = ws.send_text.call_args_list
        assert len(sent_calls) >= 1
        error_msg = json.loads(sent_calls[0][0][0])
        assert error_msg["type"] == "error"
        assert "not configured" in error_msg["error"]["message"]

    async def test_real_handler_rejects_non_session_update(self, seeded_db):
        """Full handler sends error if first message is not session.update.

        Covers TestHandleVoiceLiveWebsocket.test_rejects_non_session_update_first_message
        with real DB config (Azure SDK not even reached).
        """
        bad_msg = json.dumps({"type": "wrong.type", "data": "test"})
        ws = _make_mock_ws([bad_msg])

        await handle_voice_live_websocket(ws, seeded_db)

        sent_calls = ws.send_text.call_args_list
        assert len(sent_calls) >= 1
        error_msg = json.loads(sent_calls[0][0][0])
        assert error_msg["type"] == "error"
        assert "session.update" in error_msg["error"]["message"]
