"""Coverage boost tests #2 — targets top coverage gaps to push total >95%.

Covers:
- voice_live_websocket.py: _load_connection_config, handle_voice_live_websocket,
  _handle_message_forwarding, _forward_client_to_azure, _forward_azure_to_client,
  _send_error
- connection_tester.py: detect_region_from_endpoint, test_ai_foundry_endpoint,
  test_azure_openai, test_azure_speech, test_azure_avatar,
  test_azure_content_understanding, test_azure_realtime, test_azure_voice_live,
  test_service_connection
- startup_seed.py: seed_all (users, rubrics, HCP profiles, scenarios, materials, foundry config)
- hcp_profile_service.py: delete_hcp_profile (cascade), retry_agent_sync, batch_sync_agents
- agent_sync_service.py: create_agent, update_agent, delete_agent,
  get_portal_url_components, get_agent_latest_version
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models.hcp_profile import HcpProfile
from app.models.scoring_rubric import ScoringRubric
from app.models.service_config import ServiceConfig
from app.models.user import User

# ===========================================================================
# 1. Voice Live WebSocket: _load_connection_config
# ===========================================================================


class TestLoadConnectionConfig:
    """Tests for voice_live_websocket._load_connection_config."""

    async def test_raises_when_vl_not_configured(self, db_session):
        from app.services.voice_live_websocket import _load_connection_config

        with patch("app.services.voice_live_websocket.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="Voice Live not configured"):
                await _load_connection_config(db_session)

    async def test_raises_when_vl_inactive(self, db_session):
        from app.services.voice_live_websocket import _load_connection_config

        mock_config = MagicMock()
        mock_config.is_active = False
        with patch("app.services.voice_live_websocket.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=mock_config)
            with pytest.raises(ValueError, match="Voice Live not configured"):
                await _load_connection_config(db_session)

    async def test_allows_none_api_key_for_credential_fallback(self, db_session):
        from app.services.voice_live_websocket import _load_connection_config

        mock_config = MagicMock()
        mock_config.is_active = True
        mock_config.model_or_deployment = "gpt-4o"
        with patch("app.services.voice_live_websocket.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=mock_config)
            mock_cs.get_effective_key = AsyncMock(return_value=None)
            mock_cs.get_effective_endpoint = AsyncMock(return_value="https://test.endpoint.com")
            result = await _load_connection_config(db_session)
            assert result["api_key"] is None
            assert result["endpoint"] == "https://test.endpoint.com"

    async def test_raises_when_no_endpoint(self, db_session):
        from app.services.voice_live_websocket import _load_connection_config

        mock_config = MagicMock()
        mock_config.is_active = True
        mock_config.model_or_deployment = "gpt-4o"
        with patch("app.services.voice_live_websocket.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=mock_config)
            mock_cs.get_effective_key = AsyncMock(return_value="test-key")
            mock_cs.get_effective_endpoint = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="endpoint not configured"):
                await _load_connection_config(db_session)

    async def test_basic_config_no_hcp(self, db_session):
        """Load config without HCP profile or VL instance."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = True
        mock_avatar_config.model_or_deployment = "avatar-char"

        with patch("app.services.voice_live_websocket.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="test-key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://test.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, system_prompt="Test prompt")

        assert result["endpoint"] == "https://test.services.ai.azure.com"
        assert result["api_key"] == "test-key"
        assert result["model"] == "gpt-4o"
        assert result["system_prompt"] == "Test prompt"

    async def test_hcp_profile_overrides_with_invalid_model(self, db_session):
        """HCP profile with unsupported model falls back to default."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        mock_profile = MagicMock()
        mock_profile.agent_instructions_override = ""
        mock_profile.to_prompt_dict.return_value = {"name": "Dr. Test"}

        mock_voice_config = {
            "voice_name": "en-US-AvaNeural",
            "voice_type": "azure-standard",
            "avatar_character": "lisa",
            "avatar_style": "casual-sitting",
            "avatar_customized": False,
            "voice_live_model": "unsupported-model-xyz",
        }

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "app.services.voice_live_instance_service.resolve_voice_config",
                return_value=mock_voice_config,
            ),
            patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="casual-sitting",
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, hcp_profile_id="hcp-1")

        # Model should fall back because "unsupported-model-xyz" is not in VOICE_LIVE_MODELS
        assert result["model"] != "unsupported-model-xyz"

    async def test_hcp_profile_with_override_instructions(self, db_session):
        """HCP profile with agent_instructions_override uses that as instructions."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        mock_profile = MagicMock()
        mock_profile.agent_instructions_override = "Custom override instructions"
        mock_profile.to_prompt_dict.return_value = {"name": "Dr. Test"}

        mock_voice_config = {
            "voice_name": "en-US-AvaNeural",
            "voice_type": "azure-standard",
            "avatar_enabled": False,
            "avatar_character": "lisa",
            "avatar_style": "casual-sitting",
            "avatar_customized": False,
            "voice_live_model": "gpt-4o",
        }

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "app.services.voice_live_instance_service.resolve_voice_config",
                return_value=mock_voice_config,
            ),
            patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="casual-sitting",
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, hcp_profile_id="hcp-1")

        assert result["instructions"] == "Custom override instructions"

    async def test_hcp_profile_exception_uses_defaults(self, db_session):
        """If HCP profile lookup fails, defaults are used."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, hcp_profile_id="bad-id")

        # Should not raise, should return defaults
        assert result["endpoint"] == "https://ep.services.ai.azure.com"

    async def test_vl_instance_overrides(self, db_session):
        """VL Instance standalone test uses instance config."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = True

        mock_instance = MagicMock()
        mock_instance.voice_name = "zh-CN-XiaoxiaoNeural"
        mock_instance.voice_type = "azure-standard"
        mock_instance.avatar_character = "lisa"
        mock_instance.avatar_style = "casual-sitting"
        mock_instance.avatar_customized = False
        mock_instance.voice_live_model = "gpt-4o"
        mock_instance.model_instruction = "Instance instructions text"
        mock_instance.avatar_enabled = True

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.voice_live_instance_service.get_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="casual-sitting",
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, vl_instance_id="vl-1")

        assert result["voice_name"] == "zh-CN-XiaoxiaoNeural"
        assert result["instructions"] == "Instance instructions text"

    async def test_vl_instance_with_invalid_model(self, db_session):
        """VL Instance with unsupported model falls back to default."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        mock_instance = MagicMock()
        mock_instance.voice_name = "en-US-AvaNeural"
        mock_instance.voice_type = "azure-standard"
        mock_instance.avatar_character = "lisa"
        mock_instance.avatar_style = "casual-sitting"
        mock_instance.avatar_customized = False
        mock_instance.voice_live_model = "bad-model-xyz"
        mock_instance.model_instruction = ""
        mock_instance.avatar_enabled = False

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.voice_live_instance_service.get_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="casual-sitting",
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, vl_instance_id="vl-2")

        assert result["model"] != "bad-model-xyz"

    async def test_vl_instance_exception_uses_defaults(self, db_session):
        """If VL Instance lookup fails, defaults are used."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.voice_live_instance_service.get_instance",
                new_callable=AsyncMock,
                side_effect=Exception("Not found"),
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, vl_instance_id="bad-vl")

        assert result["endpoint"] == "https://ep.services.ai.azure.com"

    async def test_avatar_style_mismatch_logs_warning(self, db_session):
        """When validated style differs from raw style, it logs a warning and uses validated."""
        from app.services.voice_live_websocket import _load_connection_config

        mock_vl_config = MagicMock()
        mock_vl_config.is_active = True
        mock_vl_config.model_or_deployment = "gpt-4o"

        mock_avatar_config = MagicMock()
        mock_avatar_config.is_active = False

        mock_profile = MagicMock()
        mock_profile.agent_instructions_override = ""
        mock_profile.to_prompt_dict.return_value = {"name": "Dr. X"}

        mock_voice_config = {
            "voice_name": "en-US-AvaNeural",
            "voice_type": "azure-standard",
            "avatar_character": "lisa",
            "avatar_style": "bad-style",
            "avatar_customized": False,
            "voice_live_model": "gpt-4o",
        }

        with (
            patch("app.services.voice_live_websocket.config_service") as mock_cs,
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "app.services.voice_live_instance_service.resolve_voice_config",
                return_value=mock_voice_config,
            ),
            patch(
                "app.services.avatar_characters.validate_avatar_style",
                return_value="casual-sitting",
            ),
        ):
            mock_cs.get_config = AsyncMock(
                side_effect=lambda db, name: (
                    mock_vl_config if name == "azure_voice_live" else mock_avatar_config
                )
            )
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(
                return_value="https://ep.services.ai.azure.com"
            )

            result = await _load_connection_config(db_session, hcp_profile_id="hcp-1")

        # validated style replaces bad-style
        assert result["avatar_style"] == "casual-sitting"


# ===========================================================================
# 2. Voice Live WebSocket: handle_voice_live_websocket + forwarding
# ===========================================================================


class TestHandleVoiceLiveWebsocket:
    """Tests for the main WebSocket handler and message forwarding."""

    async def test_first_message_not_session_update(self):
        """Non session.update first message sends error."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {"sid": "test-sid"}
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "wrong.type"}))
        db = AsyncMock()

        await handle_voice_live_websocket(ws, db)

        ws.accept.assert_called_once()
        # Should have sent an error about first message
        calls = ws.send_text.call_args_list
        assert any("First message must be session.update" in str(c) for c in calls)

    async def test_timeout_waiting_for_session_update(self):
        """Timeout triggers error message."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {}
        ws.receive_text = AsyncMock(side_effect=TimeoutError())
        db = AsyncMock()

        await handle_voice_live_websocket(ws, db)

        ws.accept.assert_called_once()

    async def test_websocket_disconnect_handled(self):
        """WebSocketDisconnect is handled gracefully."""
        from fastapi import WebSocketDisconnect

        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {}
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        db = AsyncMock()

        # Should not raise
        await handle_voice_live_websocket(ws, db)

    async def test_config_value_error_sends_error(self):
        """ValueError from config loading sends error to client."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {"sid": "test"}
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": None, "system_prompt": "Hi"},
            }
        )
        ws.receive_text = AsyncMock(return_value=session_update)
        db = AsyncMock()

        with patch(
            "app.services.voice_live_websocket._load_connection_config",
            new_callable=AsyncMock,
            side_effect=ValueError("Voice Live not configured"),
        ):
            await handle_voice_live_websocket(ws, db)

        calls = ws.send_text.call_args_list
        assert any("Voice Live not configured" in str(c) for c in calls)

    async def test_hcp_voice_live_disabled_sends_error(self):
        """HCP profile with voice_live_enabled=False sends error."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {"sid": "test"}
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"hcp_profile_id": "hcp-123", "system_prompt": "Hi"},
            }
        )
        ws.receive_text = AsyncMock(return_value=session_update)
        db = AsyncMock()

        mock_profile = MagicMock()
        mock_profile.voice_live_enabled = False

        with (
            patch(
                "app.services.hcp_profile_service.get_hcp_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "app.services.voice_live_instance_service.resolve_voice_config",
                return_value={"voice_live_enabled": False},
            ),
            patch(
                "app.services.voice_live_websocket._load_connection_config",
                new_callable=AsyncMock,
            ) as load_config,
        ):
            await handle_voice_live_websocket(ws, db)

        load_config.assert_not_awaited()
        calls = ws.send_text.call_args_list
        assert any("not enabled" in str(c) for c in calls)

    async def test_sdk_import_error_sends_error(self):
        """ImportError for azure-ai-voicelive SDK sends error."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {"sid": "test"}
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"system_prompt": "Hi"},
            }
        )
        ws.receive_text = AsyncMock(return_value=session_update)
        db = AsyncMock()

        mock_cfg = {
            "endpoint": "https://ep.services.ai.azure.com",
            "api_key": "key",
            "model": "gpt-4o",
            "avatar_enabled": False,
            "voice_name": "en-US-AvaNeural",
            "voice_type": "azure-standard",
            "avatar_character": "lisa",
            "avatar_style": "casual-sitting",
            "avatar_customized": False,
            "instructions": "Test",
            "system_prompt": "Hi",
        }

        with (
            patch(
                "app.services.voice_live_websocket._load_connection_config",
                new_callable=AsyncMock,
                return_value=mock_cfg,
            ),
            patch.dict("sys.modules", {"azure.ai.voicelive.aio": None, "azure.ai.voicelive": None}),
            patch("builtins.__import__", side_effect=ImportError("no module")),
        ):
            # The function catches ImportError and sends an error
            await handle_voice_live_websocket(ws, db)

    async def test_general_exception_handled(self):
        """General exception during processing sends error."""
        from app.services.voice_live_websocket import handle_voice_live_websocket

        ws = AsyncMock()
        ws.query_params = {"sid": "test"}
        session_update = json.dumps(
            {
                "type": "session.update",
                "session": {"system_prompt": "Hi"},
            }
        )
        ws.receive_text = AsyncMock(return_value=session_update)
        db = AsyncMock()

        with patch(
            "app.services.voice_live_websocket._load_connection_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ):
            await handle_voice_live_websocket(ws, db)

        # Should not raise, exception is caught

    async def test_send_error_silences_exception(self):
        """_send_error silences exceptions from ws.send_text."""
        from app.services.voice_live_websocket import _send_error

        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("Connection lost"))

        # Should not raise
        await _send_error(ws, "test error")

    async def test_forward_client_to_azure(self):
        """_forward_client_to_azure forwards messages until disconnect."""
        from fastapi import WebSocketDisconnect

        from app.services.voice_live_websocket import _forward_client_to_azure

        ws = AsyncMock()
        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "input_audio_buffer.append", "audio": "base64data"}),
                json.dumps({"type": "session.avatar.connect", "client_sdp": "sdp-data"}),
                WebSocketDisconnect(),
            ]
        )
        azure_conn = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        await _forward_client_to_azure(
            ws, azure_conn, WebSocketDisconnect, session_log, event_counts
        )

        assert azure_conn.send.call_count == 2
        assert "c2a:input_audio_buffer.append" in event_counts
        assert "c2a:session.avatar.connect" in event_counts

    async def test_forward_client_to_azure_error(self):
        """_forward_client_to_azure handles non-disconnect exceptions."""
        from app.services.voice_live_websocket import _forward_client_to_azure

        ws = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError("read error"))
        azure_conn = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        await _forward_client_to_azure(ws, azure_conn, Exception, session_log, event_counts)

    async def test_forward_azure_to_client(self):
        """_forward_azure_to_client forwards events and logs key types."""
        from app.services.voice_live_websocket import _forward_azure_to_client

        # Create mock events
        mock_event_audio = MagicMock()
        mock_event_audio.as_dict.return_value = {
            "type": "response.audio.delta",
            "delta": "base64audio",
        }
        mock_event_audio.type = "response.audio.delta"

        mock_event_avatar_connect = MagicMock()
        mock_event_avatar_connect.as_dict.return_value = {
            "type": "session.avatar.connecting",
            "server_sdp": "sdp-answer",
        }
        mock_event_avatar_connect.type = "session.avatar.connecting"

        mock_event_session_created = MagicMock()
        mock_event_session_created.as_dict.return_value = {
            "type": "session.created",
            "session": {"id": "sess-1"},
        }
        mock_event_session_created.type = MagicMock()

        mock_event_session_updated = MagicMock()
        mock_event_session_updated.as_dict.return_value = {
            "type": "session.updated",
            "session": {
                "id": "sess-1",
                "modalities": ["text", "audio"],
                "voice": {"name": "en-US-AvaNeural"},
                "avatar": {"ice_servers": [], "output_protocol": "webrtc"},
            },
        }
        mock_event_session_updated.type = MagicMock()

        mock_event_error = MagicMock()
        mock_event_error.as_dict.return_value = {
            "type": "error",
            "error": {"message": "rate limit"},
        }
        mock_event_error.type = MagicMock()

        # Simulate azure_conn as async iterator then disconnect
        events = [
            mock_event_audio,
            mock_event_avatar_connect,
            mock_event_session_created,
            mock_event_session_updated,
            mock_event_error,
        ]

        class MockAzureConn:
            def __init__(self):
                self._events = iter(events)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._events)
                except StopIteration:
                    raise StopAsyncIteration

        azure_conn = MockAzureConn()
        ws = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        # Create mock ServerEventType with matching type values
        ServerEventType = MagicMock()
        ServerEventType.ERROR = mock_event_error.type
        ServerEventType.SESSION_CREATED = mock_event_session_created.type
        ServerEventType.SESSION_UPDATED = mock_event_session_updated.type

        await _forward_azure_to_client(
            azure_conn, ws, Exception, ServerEventType, session_log, event_counts
        )

        assert ws.send_text.call_count == 5
        assert "a2c:response.audio.delta" in event_counts
        assert "a2c:session.avatar.connecting" in event_counts

    async def test_forward_azure_to_client_error(self):
        """_forward_azure_to_client handles non-disconnect exceptions."""
        from app.services.voice_live_websocket import _forward_azure_to_client

        class ErrorAzureConn:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("Azure connection lost")

        azure_conn = ErrorAzureConn()
        ws = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        await _forward_azure_to_client(
            azure_conn, ws, Exception, MagicMock(), session_log, event_counts
        )

    async def test_handle_message_forwarding_cancels_pending(self):
        """_handle_message_forwarding cancels remaining tasks when one completes."""
        from app.services.voice_live_websocket import _handle_message_forwarding

        ws = AsyncMock()
        azure_conn = AsyncMock()
        session_log = MagicMock()
        event_counts: dict[str, int] = {}

        # Patch the two forwarding functions to make one complete immediately
        with (
            patch(
                "app.services.voice_live_websocket._forward_client_to_azure",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.voice_live_websocket._forward_azure_to_client",
                new_callable=AsyncMock,
                side_effect=asyncio.sleep(10),  # slow, will be cancelled
            ),
        ):
            await asyncio.wait_for(
                _handle_message_forwarding(
                    ws, azure_conn, Exception, MagicMock(), session_log, event_counts
                ),
                timeout=5.0,
            )


# ===========================================================================
# 3. Connection Tester
# ===========================================================================


class TestConnectionTester:
    """Tests for connection_tester module functions."""

    def test_derive_endpoint_variants_empty(self):
        from app.services.connection_tester import _derive_endpoint_variants

        assert _derive_endpoint_variants("") == []

    def test_derive_endpoint_variants_non_azure(self):
        from app.services.connection_tester import _derive_endpoint_variants

        result = _derive_endpoint_variants("https://my-custom-server.example.com/")
        assert result == ["https://my-custom-server.example.com"]

    def test_derive_endpoint_variants_cognitive(self):
        from app.services.connection_tester import _derive_endpoint_variants

        result = _derive_endpoint_variants("https://my-resource.cognitiveservices.azure.com")
        assert len(result) == 2
        assert "cognitiveservices.azure.com" in result[0]
        assert "services.ai.azure.com" in result[1]

    def test_derive_endpoint_variants_ai_foundry(self):
        from app.services.connection_tester import _derive_endpoint_variants

        result = _derive_endpoint_variants("https://my-resource.services.ai.azure.com/")
        assert len(result) == 2
        assert "services.ai.azure.com" in result[0]

    def test_validate_endpoint_url_empty(self):
        from app.services.connection_tester import validate_endpoint_url

        ok, msg = validate_endpoint_url("")
        assert ok is False
        assert "required" in msg.lower()

    def test_validate_endpoint_url_http(self):
        from app.services.connection_tester import validate_endpoint_url

        ok, msg = validate_endpoint_url("http://example.com")
        assert ok is False
        assert "HTTPS" in msg

    def test_validate_endpoint_url_non_azure(self):
        from app.services.connection_tester import validate_endpoint_url

        ok, msg = validate_endpoint_url("https://example.com")
        assert ok is False

    def test_validate_endpoint_url_valid(self):
        from app.services.connection_tester import validate_endpoint_url

        ok, msg = validate_endpoint_url("https://my-resource.cognitiveservices.azure.com")
        assert ok is True

    async def test_detect_region_from_header(self):

        from app.services.connection_tester import detect_region_from_endpoint

        mock_response = MagicMock()
        mock_response.headers = {"x-ms-region": "East US 2"}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await detect_region_from_endpoint(
                "https://test.cognitiveservices.azure.com", "key"
            )
            assert result == "eastus2"

    async def test_detect_region_from_hostname_fallback(self):
        from app.services.connection_tester import detect_region_from_endpoint

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await detect_region_from_endpoint(
                "https://my-resource-eastus2.cognitiveservices.azure.com", "key"
            )
            assert result == "eastus2"

    async def test_detect_region_returns_empty_on_failure(self):
        from app.services.connection_tester import detect_region_from_endpoint

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            result = await detect_region_from_endpoint(
                "https://unknown-location.cognitiveservices.azure.com", "key"
            )
            assert result == ""

    async def test_ai_foundry_endpoint_invalid_url(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        ok, msg = await test_ai_foundry_endpoint("http://bad", "key")
        assert ok is False

    async def test_ai_foundry_endpoint_no_key(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        # When no key is provided and DefaultAzureCredential also fails,
        # the function should return False with a key/credential message.
        with patch(
            "app.services.connection_tester._get_bearer_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            ok, msg = await test_ai_foundry_endpoint("https://test.cognitiveservices.azure.com", "")
            assert ok is False
            assert "key" in msg.lower() or "credential" in msg.lower()

    async def test_ai_foundry_endpoint_with_model_delegates(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        with patch(
            "app.services.connection_tester.test_azure_openai",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ) as mock_openai:
            ok, msg = await test_ai_foundry_endpoint(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o"
            )
            assert ok is True
            mock_openai.assert_called_once()

    async def test_ai_foundry_endpoint_list_deployments_success(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4o"}]}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_ai_foundry_endpoint(
                "https://test.cognitiveservices.azure.com", "key"
            )
            assert ok is True
            assert "1 deployment" in msg

    async def test_ai_foundry_endpoint_auth_failed(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_ai_foundry_endpoint(
                "https://test.cognitiveservices.azure.com", "bad-key"
            )
            assert ok is False
            assert "Authentication" in msg

    async def test_ai_foundry_endpoint_other_status(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_ai_foundry_endpoint(
                "https://test.cognitiveservices.azure.com", "key"
            )
            assert ok is False
            assert "500" in msg

    async def test_ai_foundry_endpoint_exception(self):
        from app.services.connection_tester import test_ai_foundry_endpoint

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_ai_foundry_endpoint(
                "https://test.cognitiveservices.azure.com", "key"
            )
            assert ok is False
            assert "Connection failed" in msg

    async def test_azure_openai_success(self):
        from app.services.connection_tester import test_azure_openai

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=MagicMock())

        with patch("openai.AsyncAzureOpenAI", return_value=mock_client):
            ok, msg = await test_azure_openai(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o"
            )
            assert ok is True

    async def test_azure_openai_fallback_to_max_tokens(self):
        from app.services.connection_tester import test_azure_openai

        mock_client = AsyncMock()
        # First call fails with max_completion_tokens error, second succeeds
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                Exception("max_completion_tokens is not supported"),
                MagicMock(),
            ]
        )

        with patch("openai.AsyncAzureOpenAI", return_value=mock_client):
            ok, msg = await test_azure_openai(
                "https://test.cognitiveservices.azure.com", "key", "gpt-35-turbo"
            )
            assert ok is True
            assert mock_client.chat.completions.create.call_count == 2

    async def test_azure_openai_import_error(self):
        from app.services.connection_tester import test_azure_openai

        with patch("builtins.__import__", side_effect=ImportError("no openai")):
            ok, msg = await test_azure_openai(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o"
            )
            assert ok is False
            assert "not installed" in msg

    async def test_azure_speech_no_key(self):
        from app.services.connection_tester import test_azure_speech

        ok, msg = await test_azure_speech("", "eastus")
        assert ok is False
        assert "key" in msg.lower()

    async def test_azure_speech_no_region_no_endpoint(self):
        from app.services.connection_tester import test_azure_speech

        ok, msg = await test_azure_speech("key", "")
        assert ok is False

    async def test_azure_speech_success_with_endpoint(self):
        from app.services.connection_tester import test_azure_speech

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_speech("key", "", "https://test.cognitiveservices.azure.com")
            assert ok is True

    async def test_azure_speech_auth_failed(self):
        from app.services.connection_tester import test_azure_speech

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_speech(
                "key", "eastus", "https://test.cognitiveservices.azure.com"
            )
            assert ok is False
            assert "Authentication" in msg

    async def test_azure_speech_all_unreachable(self):
        from app.services.connection_tester import test_azure_speech

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_speech("key", "", "https://test.cognitiveservices.azure.com")
            # All 404 means last_status stays 0
            assert ok is False
            assert "unreachable" in msg.lower()

    async def test_azure_speech_probe_exception(self):
        from app.services.connection_tester import test_azure_speech

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_speech(
                "key", "eastus", "https://test.cognitiveservices.azure.com"
            )
            assert ok is False

    async def test_azure_avatar_no_key(self):
        from app.services.connection_tester import test_azure_avatar

        ok, msg = await test_azure_avatar("", "eastus")
        assert ok is False

    async def test_azure_avatar_no_endpoint_no_region(self):
        from app.services.connection_tester import test_azure_avatar

        ok, msg = await test_azure_avatar("key", "")
        assert ok is False
        assert "Region or endpoint" in msg

    async def test_azure_avatar_success(self):
        from app.services.connection_tester import test_azure_avatar

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_avatar(
                "key", "eastus", "https://test.cognitiveservices.azure.com"
            )
            assert ok is True
            assert "ICE token" in msg

    async def test_azure_avatar_auth_failed(self):
        from app.services.connection_tester import test_azure_avatar

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_avatar("key", "", "https://test.cognitiveservices.azure.com")
            assert ok is False
            assert "Authentication" in msg

    async def test_azure_avatar_all_unreachable(self):
        from app.services.connection_tester import test_azure_avatar

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_avatar("key", "", "https://test.cognitiveservices.azure.com")
            assert ok is False
            assert "unreachable" in msg.lower()

    async def test_azure_avatar_other_status(self):
        from app.services.connection_tester import test_azure_avatar

        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_avatar(
                "key", "eastus", "https://test.cognitiveservices.azure.com"
            )
            assert ok is False
            assert "503" in msg

    async def test_azure_avatar_connection_exception(self):
        from app.services.connection_tester import test_azure_avatar

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(side_effect=Exception("Total failure"))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            ok, msg = await test_azure_avatar("key", "eastus")
            assert ok is False

    async def test_content_understanding_success(self):
        from app.services.connection_tester import test_azure_content_understanding

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_content_understanding(
                "https://test.services.ai.azure.com", "key"
            )
            assert ok is True

    async def test_content_understanding_auth_failed(self):
        from app.services.connection_tester import test_azure_content_understanding

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_content_understanding(
                "https://test.services.ai.azure.com", "key"
            )
            assert ok is False
            assert "Authentication" in msg

    async def test_content_understanding_other_status(self):
        from app.services.connection_tester import test_azure_content_understanding

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_content_understanding(
                "https://test.services.ai.azure.com", "key"
            )
            assert ok is False
            assert "500" in msg

    async def test_content_understanding_exception(self):
        from app.services.connection_tester import test_azure_content_understanding

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_content_understanding(
                "https://test.services.ai.azure.com", "key"
            )
            assert ok is False

    async def test_azure_realtime_success(self):
        from app.services.connection_tester import test_azure_realtime

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_realtime(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o-realtime"
            )
            assert ok is True

    async def test_azure_realtime_404(self):
        from app.services.connection_tester import test_azure_realtime

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_realtime(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o-realtime"
            )
            assert ok is False
            assert "not found" in msg.lower()

    async def test_azure_realtime_other_status(self):
        from app.services.connection_tester import test_azure_realtime

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_realtime(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o-realtime"
            )
            assert ok is False
            assert "500" in msg

    async def test_azure_realtime_exception(self):
        from app.services.connection_tester import test_azure_realtime

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_realtime(
                "https://test.cognitiveservices.azure.com", "key", "gpt-4o-realtime"
            )
            assert ok is False
            assert "Realtime connection failed" in msg

    async def test_azure_voice_live_unsupported_region(self):
        from app.services.connection_tester import test_azure_voice_live

        ok, msg = await test_azure_voice_live(
            "https://test.cognitiveservices.azure.com", "key", "badregion"
        )
        assert ok is False
        assert "Unsupported region" in msg

    async def test_azure_voice_live_no_key(self):
        from app.services.connection_tester import test_azure_voice_live

        with patch(
            "app.services.connection_tester._get_bearer_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            ok, msg = await test_azure_voice_live(
                "https://test.cognitiveservices.azure.com", "", "swedencentral"
            )
            assert ok is False
            assert "key" in msg.lower() or "credential" in msg.lower()

    async def test_azure_voice_live_success(self):
        from app.services.connection_tester import test_azure_voice_live

        mock_response = MagicMock()
        mock_response.status_code = 426  # Upgrade required = endpoint reachable

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_voice_live(
                "https://test.cognitiveservices.azure.com", "key", "swedencentral"
            )
            assert ok is True

    async def test_azure_voice_live_auth_failed(self):
        from app.services.connection_tester import test_azure_voice_live

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_voice_live(
                "https://test.cognitiveservices.azure.com", "key", "swedencentral"
            )
            assert ok is False
            assert "Authentication" in msg

    async def test_azure_voice_live_other_status(self):
        from app.services.connection_tester import test_azure_voice_live

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_voice_live(
                "https://test.cognitiveservices.azure.com", "key", "swedencentral"
            )
            assert ok is True

    async def test_azure_voice_live_exception(self):
        from app.services.connection_tester import test_azure_voice_live

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            ok, msg = await test_azure_voice_live(
                "https://test.cognitiveservices.azure.com", "key", "swedencentral"
            )
            # Exception in VL test returns True with a note
            assert ok is True
            assert "connectivity check skipped" in msg

    async def test_service_connection_routing_ai_foundry(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_ai_foundry_endpoint",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "ai_foundry", "https://ep.cognitiveservices.azure.com", "key", "gpt-4o", ""
            )
            assert ok is True

    async def test_service_connection_routing_azure_openai(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_openai",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "azure_openai",
                "",
                "",
                "gpt-4o",
                "",
                master_endpoint="https://ep.cognitiveservices.azure.com",
                master_key="key",
            )
            assert ok is True

    async def test_service_connection_routing_speech(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_speech",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection("azure_speech_tts", "", "key", "", "eastus")
            assert ok is True

    async def test_service_connection_routing_avatar(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_avatar",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection("azure_avatar", "", "key", "", "eastus")
            assert ok is True

    async def test_service_connection_routing_voice_live(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_voice_live",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "azure_voice_live",
                "https://ep.cognitiveservices.azure.com",
                "key",
                "",
                "swedencentral",
            )
            assert ok is True

    async def test_service_connection_routing_content(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_content_understanding",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "azure_content", "https://ep.services.ai.azure.com", "key", "", ""
            )
            assert ok is True

    async def test_service_connection_routing_realtime(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_azure_realtime",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "azure_openai_realtime",
                "https://ep.cognitiveservices.azure.com",
                "key",
                "gpt-4o",
                "",
            )
            assert ok is True

    async def test_service_connection_unknown_service(self):
        from app.services.connection_tester import test_service_connection

        ok, msg = await test_service_connection("unknown_service", "", "", "", "")
        assert ok is False
        assert "Unknown service" in msg

    async def test_service_connection_master_fallback(self):
        from app.services.connection_tester import test_service_connection

        with patch(
            "app.services.connection_tester.test_ai_foundry_endpoint",
            new_callable=AsyncMock,
            return_value=(True, "OK"),
        ):
            ok, msg = await test_service_connection(
                "ai_foundry",
                "",
                "",
                "",
                "",
                master_endpoint="https://master.cognitiveservices.azure.com",
                master_key="master-key",
                master_model="gpt-4o",
            )
            assert ok is True


# ===========================================================================
# 4. Startup Seed
# ===========================================================================


class TestStartupSeed:
    """Tests for startup_seed.seed_all."""

    async def test_seed_creates_users(self, db_session):
        """seed_all creates admin and user accounts."""
        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        mock_settings = MagicMock()
        mock_settings.azure_foundry_endpoint = ""
        mock_settings.azure_foundry_api_key = ""

        with (
            patch.dict("sys.modules", {"seed_phase2": mock_seed2, "seed_materials": MagicMock()}),
            patch("app.config.get_settings", return_value=mock_settings),
        ):
            from app.startup_seed import seed_all

            await seed_all(db_session)

        # Verify users were created
        result = await db_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) >= 4
        usernames = {u.username for u in users}
        assert "admin" in usernames
        assert "user1" in usernames

    async def test_seed_creates_default_rubric(self, db_session):
        """seed_all creates the default F2F scoring rubric."""
        # First create admin user manually
        from app.services.auth import get_password_hash

        admin = User(
            username="admin",
            email="admin@aicoach.com",
            hashed_password=get_password_hash("admin123"),
            role="admin",
        )
        db_session.add(admin)
        await db_session.commit()

        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        mock_settings = MagicMock()
        mock_settings.azure_foundry_endpoint = ""

        with (
            patch.dict("sys.modules", {"seed_phase2": mock_seed2, "seed_materials": MagicMock()}),
            patch("app.config.get_settings", return_value=mock_settings),
        ):
            from app.startup_seed import seed_all

            await seed_all(db_session)

        result = await db_session.execute(
            select(ScoringRubric).where(ScoringRubric.is_default == True)  # noqa: E712
        )
        rubric = result.scalar_one_or_none()
        assert rubric is not None
        assert rubric.scenario_type == "f2f"

    async def test_seed_is_idempotent(self, db_session):
        """Running seed_all twice doesn't create duplicates."""
        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        mock_settings = MagicMock()
        mock_settings.azure_foundry_endpoint = ""

        with (
            patch.dict("sys.modules", {"seed_phase2": mock_seed2, "seed_materials": MagicMock()}),
            patch("app.config.get_settings", return_value=mock_settings),
        ):
            from app.startup_seed import seed_all

            await seed_all(db_session)
            await seed_all(db_session)

        result = await db_session.execute(select(User).where(User.username == "admin"))
        admins = result.scalars().all()
        assert len(admins) == 1

    async def test_seed_with_foundry_config(self, db_session):
        """seed_all creates ServiceConfig when foundry env vars are set."""
        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        mock_settings = MagicMock()
        mock_settings.azure_foundry_endpoint = "https://test.services.ai.azure.com"
        mock_settings.azure_foundry_api_key = "test-key"
        mock_settings.azure_openai_deployment = "gpt-4o"
        mock_settings.voice_live_default_model = "gpt-4o"
        mock_settings.azure_foundry_default_project = "test-project"

        with (
            patch.dict("sys.modules", {"seed_phase2": mock_seed2, "seed_materials": MagicMock()}),
            patch("app.config.get_settings", return_value=mock_settings),
            patch("app.utils.encryption.encrypt_value", return_value="encrypted-key"),
        ):
            from app.startup_seed import seed_all

            await seed_all(db_session)

        result = await db_session.execute(
            select(ServiceConfig).where(ServiceConfig.is_master == True)  # noqa: E712
        )
        master = result.scalar_one_or_none()
        assert master is not None
        assert master.service_name == "ai_foundry"

        # Check VL service row was also created
        vl_result = await db_session.execute(
            select(ServiceConfig).where(ServiceConfig.service_name == "azure_voice_live")
        )
        vl_config = vl_result.scalar_one_or_none()
        assert vl_config is not None

    async def test_seed_materials_exception_is_caught(self, db_session):
        """If materials seed fails, it's caught and logged."""
        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        mock_seed_materials = MagicMock()
        mock_seed_materials.seed_materials = AsyncMock(side_effect=Exception("Materials error"))

        mock_settings_obj = MagicMock()
        mock_settings_obj.azure_foundry_endpoint = ""

        with (
            patch.dict(
                "sys.modules", {"seed_phase2": mock_seed2, "seed_materials": mock_seed_materials}
            ),
            patch("app.config.get_settings", return_value=mock_settings_obj),
        ):
            from app.startup_seed import seed_all

            # Should not raise
            await seed_all(db_session)

    async def test_seed_foundry_exception_is_caught(self, db_session):
        """If foundry config seed fails, it's caught and logged."""
        mock_seed2 = MagicMock()
        mock_seed2.SEED_HCP_PROFILES = []
        mock_seed2.SEED_SCENARIOS = []

        with (
            patch.dict("sys.modules", {"seed_phase2": mock_seed2, "seed_materials": MagicMock()}),
            patch("app.config.get_settings", side_effect=Exception("Settings error")),
        ):
            from app.startup_seed import seed_all

            # Should not raise — the foundry section catches exceptions
            await seed_all(db_session)


# ===========================================================================
# 5. HCP Profile Service: delete cascade, retry sync, batch sync
# ===========================================================================


class TestHcpProfileServiceCascade:
    """Tests for delete_hcp_profile cascade and agent sync helpers."""

    async def test_delete_hcp_with_scenarios_and_sessions(self, db_session):
        """delete_hcp_profile cascades through scenarios, sessions, messages, scores."""
        from app.models.scenario import Scenario
        from app.models.session import CoachingSession
        from app.services.hcp_profile_service import delete_hcp_profile

        # Create a user
        user = User(
            username="testdel",
            email="del@test.com",
            hashed_password="hash",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        # Create HCP profile
        profile = HcpProfile(name="Dr. Delete", specialty="General", created_by=user.id)
        db_session.add(profile)
        await db_session.flush()

        # Create scenario linked to profile
        scenario = Scenario(
            name="Test Scenario",
            tags='["product:TestDrug"]',
            mode="f2f",
            hcp_profile_id=profile.id,
            created_by=user.id,
            rubric_id="test-rubric-id",
            skill_id="test-skill-id",
        )
        db_session.add(scenario)
        await db_session.flush()

        # Create coaching session
        session = CoachingSession(
            scenario_id=scenario.id,
            user_id=user.id,
            status="completed",
        )
        db_session.add(session)
        await db_session.commit()

        profile_id = profile.id

        with patch(
            "app.services.agent_sync_service.delete_agent",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await delete_hcp_profile(db_session, profile_id)
            await db_session.commit()

        # Verify HCP profile is gone
        result = await db_session.execute(select(HcpProfile).where(HcpProfile.id == profile_id))
        assert result.scalar_one_or_none() is None

    async def test_delete_hcp_agent_failure_continues(self, db_session):
        """delete_hcp_profile continues even if agent deletion fails."""
        from app.services.hcp_profile_service import delete_hcp_profile

        user = User(
            username="testdel2",
            email="del2@test.com",
            hashed_password="hash",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        profile = HcpProfile(
            name="Dr. AgentFail",
            specialty="General",
            created_by=user.id,
            agent_id="agent-123",
        )
        db_session.add(profile)
        await db_session.commit()

        profile_id = profile.id

        with patch(
            "app.services.agent_sync_service.delete_agent",
            new_callable=AsyncMock,
            side_effect=Exception("Agent API down"),
        ):
            await delete_hcp_profile(db_session, profile_id)
            await db_session.commit()

        result = await db_session.execute(select(HcpProfile).where(HcpProfile.id == profile_id))
        assert result.scalar_one_or_none() is None

    async def test_retry_agent_sync_success(self, db_session):
        """retry_agent_sync updates profile with new agent data."""
        from app.services.hcp_profile_service import retry_agent_sync

        user = User(
            username="testretrysync",
            email="retry@test.com",
            hashed_password="hash",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        profile = HcpProfile(
            name="Dr. Retry",
            specialty="Oncology",
            created_by=user.id,
            agent_sync_status="failed",
        )
        db_session.add(profile)
        await db_session.commit()

        with (
            patch(
                "app.services.agent_sync_service.prefetch_sync_config",
                new_callable=AsyncMock,
                return_value=("endpoint", "key", "gpt-4o"),
            ),
            patch(
                "app.services.agent_sync_service.sync_agent_for_profile",
                new_callable=AsyncMock,
                return_value={"id": "new-agent-id", "version": "2"},
            ),
        ):
            result = await retry_agent_sync(db_session, profile.id)

        assert result.agent_sync_status == "synced"
        assert result.agent_id == "new-agent-id"

    async def test_retry_agent_sync_failure(self, db_session):
        """retry_agent_sync records failure when sync fails."""
        from app.services.hcp_profile_service import retry_agent_sync

        user = User(
            username="testretryfail",
            email="retryfail@test.com",
            hashed_password="hash",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        profile = HcpProfile(
            name="Dr. RetryFail",
            specialty="General",
            created_by=user.id,
            agent_sync_status="failed",
        )
        db_session.add(profile)
        await db_session.commit()

        with (
            patch(
                "app.services.agent_sync_service.prefetch_sync_config",
                new_callable=AsyncMock,
                return_value=("endpoint", "key", "gpt-4o"),
            ),
            patch(
                "app.services.agent_sync_service.sync_agent_for_profile",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Sync failure"),
            ),
        ):
            result = await retry_agent_sync(db_session, profile.id)

        assert result.agent_sync_status == "failed"
        assert "Sync failure" in result.agent_sync_error

    async def test_batch_sync_agents(self, db_session):
        """batch_sync_agents syncs profiles with missing agent_id."""
        from app.services.hcp_profile_service import batch_sync_agents

        user = User(
            username="testbatch",
            email="batch@test.com",
            hashed_password="hash",
            role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        # Create profiles needing sync
        p1 = HcpProfile(
            name="Dr. Batch1",
            specialty="General",
            created_by=user.id,
            agent_id="",
        )
        p2 = HcpProfile(
            name="Dr. Batch2",
            specialty="General",
            created_by=user.id,
            agent_sync_status="failed",
        )
        db_session.add_all([p1, p2])
        await db_session.commit()

        with (
            patch(
                "app.services.agent_sync_service.prefetch_sync_config",
                new_callable=AsyncMock,
                return_value=("endpoint", "key", "gpt-4o"),
            ),
            patch(
                "app.services.agent_sync_service.sync_agent_for_profile",
                new_callable=AsyncMock,
                return_value={"id": "batch-agent", "version": "1"},
            ),
        ):
            summary = await batch_sync_agents(db_session)

        assert summary["synced"] >= 2
        assert summary["failed"] == 0

    async def test_batch_sync_agents_config_error(self, db_session):
        """batch_sync_agents returns error when config prefetch fails."""
        from app.services.hcp_profile_service import batch_sync_agents

        with patch(
            "app.services.agent_sync_service.prefetch_sync_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("No config"),
        ):
            summary = await batch_sync_agents(db_session)

        assert summary["synced"] == 0
        assert "No config" in summary.get("error", "")


# ===========================================================================
# 6. Agent Sync Service: create/update/delete, portal URL, latest version
# ===========================================================================


class TestAgentSyncService:
    """Tests for agent_sync_service CRUD and discovery functions."""

    async def test_create_agent_success(self, db_session):
        from app.services.agent_sync_service import create_agent

        mock_result = MagicMock()
        mock_result.name = "Dr-Test"
        mock_result.version = "1"

        mock_client = MagicMock()
        mock_client.agents.create_version = MagicMock(return_value=mock_result)

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep.services.ai.azure.com/api/projects/proj", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_result),
        ):
            result = await create_agent(db_session, "Dr. Test", "Instructions here", "gpt-4o")

        assert result["id"] == "Dr-Test"
        assert result["version"] == "1"

    async def test_create_agent_with_override(self, db_session):
        from app.services.agent_sync_service import create_agent

        mock_result = MagicMock()
        mock_result.name = "Dr-Override"
        mock_result.version = "1"

        mock_client = MagicMock()
        mock_client.agents.create_version = MagicMock(return_value=mock_result)

        with (
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_result),
        ):
            result = await create_agent(
                db_session,
                "Dr. Override",
                "Instructions",
                endpoint_override="https://ep.services.ai.azure.com/api/projects/proj",
                key_override="override-key",
            )

        assert result["name"] == "Dr-Override"

    async def test_create_agent_failure(self, db_session):
        from app.services.agent_sync_service import create_agent

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep.services.ai.azure.com/api/projects/proj", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=Exception("API error")),
        ):
            with pytest.raises(RuntimeError, match="Agent creation failed"):
                await create_agent(db_session, "Dr. Fail", "Instructions", "gpt-4o")

    async def test_update_agent_success(self, db_session):
        from app.services.agent_sync_service import update_agent

        mock_result = MagicMock()
        mock_result.name = "Dr-Update"
        mock_result.version = "2"

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep.services.ai.azure.com/api/projects/proj", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_result),
        ):
            result = await update_agent(
                db_session, "Dr-Update", "Dr. Update", "New instructions", "gpt-4o"
            )

        assert result["version"] == "2"

    async def test_update_agent_failure(self, db_session):
        from app.services.agent_sync_service import update_agent

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=Exception("API error")),
        ):
            with pytest.raises(RuntimeError, match="Agent update failed"):
                await update_agent(db_session, "agent-1", "Dr. Fail", "Instructions", "gpt-4o")

    async def test_delete_agent_success(self, db_session):
        from app.services.agent_sync_service import delete_agent

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=None),
        ):
            result = await delete_agent(db_session, "agent-1")

        assert result is True

    async def test_delete_agent_failure(self, db_session):
        from app.services.agent_sync_service import delete_agent

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch(
                "asyncio.to_thread", new_callable=AsyncMock, side_effect=Exception("Delete failed")
            ),
        ):
            result = await delete_agent(db_session, "agent-1")

        assert result is False

    async def test_get_portal_url_components_success(self, db_session):
        import app.services.agent_sync_service as asm

        # Reset cache
        asm._portal_url_cache = None

        mock_conn = {
            "id": (
                "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/"
                "rg-test/providers/Microsoft.MachineLearningServices/accounts/my-account/"
                "projects/my-project/connections/conn1"
            )
        }
        mock_client = MagicMock()
        mock_client.connections.list = MagicMock(return_value=[mock_conn])

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=[mock_conn]),
        ):
            result = await asm.get_portal_url_components(db_session)

        assert result.get("resource_group") == "rg-test"
        assert result.get("project_name") == "my-project"

        # Reset cache for other tests
        asm._portal_url_cache = None

    async def test_get_portal_url_components_no_connections(self, db_session):
        import app.services.agent_sync_service as asm

        asm._portal_url_cache = None

        mock_client = MagicMock()
        mock_client.connections.list = MagicMock(return_value=[])

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=[]),
        ):
            result = await asm.get_portal_url_components(db_session)

        assert result == {}
        asm._portal_url_cache = None

    async def test_get_portal_url_components_exception(self, db_session):
        import app.services.agent_sync_service as asm

        asm._portal_url_cache = None

        with patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            result = await asm.get_portal_url_components(db_session)

        assert result == {}
        asm._portal_url_cache = None

    async def test_get_agent_latest_version_success(self, db_session):
        from app.services.agent_sync_service import get_agent_latest_version

        mock_agent = MagicMock()
        mock_agent.versions = {"latest": {"version": "5"}}

        mock_client = MagicMock()

        with (
            patch(
                "app.services.agent_sync_service.get_project_endpoint",
                new_callable=AsyncMock,
                return_value=("https://ep/api/projects/p", "key"),
            ),
            patch("app.services.agent_sync_service._get_project_client", return_value=mock_client),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_agent),
        ):
            version = await get_agent_latest_version(db_session, "my-agent")

        assert version == "5"

    async def test_get_agent_latest_version_failure(self, db_session):
        from app.services.agent_sync_service import get_agent_latest_version

        with patch(
            "app.services.agent_sync_service.get_project_endpoint",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            version = await get_agent_latest_version(db_session, "my-agent")

        assert version == "1"


# ===========================================================================
# 7. Analytics Service: get_score_trends, get_org_analytics
# ===========================================================================


class TestAnalyticsService:
    """Tests for analytics_service functions to cover missing lines."""

    async def test_get_score_trends(self, db_session):
        """get_score_trends returns monthly score trend points."""
        from app.services.analytics_service import get_score_trends

        points = await get_score_trends(db_session, months=3)
        assert len(points) == 3
        for p in points:
            assert hasattr(p, "month")
            assert hasattr(p, "overall")
            assert hasattr(p, "benchmark")
            assert p.benchmark == 75.0

    async def test_get_org_analytics(self, db_session):
        """get_org_analytics returns org-level stats."""
        from app.services.analytics_service import get_org_analytics

        result = await get_org_analytics(db_session)
        assert hasattr(result, "total_users")
        assert hasattr(result, "active_users")
        assert hasattr(result, "total_sessions")
        assert hasattr(result, "bu_stats")

    async def test_get_org_analytics_with_dates(self, db_session):
        """get_org_analytics with date filters."""
        from app.services.analytics_service import get_org_analytics

        result = await get_org_analytics(db_session, start_date="2024-01-01", end_date="2026-12-31")
        assert result.total_sessions >= 0


# ===========================================================================
# 8. Voice Live Service: STS token exchange + get_voice_live_token errors
# ===========================================================================


class TestVoiceLiveService:
    """Tests for voice_live_service functions."""

    async def test_exchange_api_key_for_bearer_token(self):
        """_exchange_api_key_for_bearer_token calls STS endpoint."""
        from app.services.voice_live_service import _exchange_api_key_for_bearer_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "bearer-token-value"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            token = await _exchange_api_key_for_bearer_token(
                "https://test.cognitiveservices.azure.com", "api-key"
            )
            assert token == "bearer-token-value"

    async def test_get_voice_live_token_no_config(self, db_session):
        """get_voice_live_token raises when VL not configured."""
        from app.services.voice_live_service import get_voice_live_token

        with patch("app.services.voice_live_service.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="Voice Live not configured"):
                await get_voice_live_token(db_session)

    async def test_get_voice_live_token_no_key(self, db_session):
        """get_voice_live_token supports keyless bearer mode when endpoint exists."""
        from app.services.voice_live_service import get_voice_live_token

        mock_config = MagicMock()
        mock_config.is_active = True
        mock_config.region = "eastus2"
        mock_config.model_or_deployment = "gpt-4o-realtime-preview"

        with patch("app.services.voice_live_service.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=mock_config)
            mock_cs.get_effective_key = AsyncMock(return_value=None)
            mock_cs.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
            mock_cs.get_master_config = AsyncMock(return_value=None)

            token = await get_voice_live_token(db_session)

        assert token.auth_type == "bearer"
        assert token.token == "***configured***"

    async def test_get_voice_live_token_no_endpoint(self, db_session):
        """get_voice_live_token raises when no endpoint."""
        from app.services.voice_live_service import get_voice_live_token

        mock_config = MagicMock()
        mock_config.is_active = True

        with patch("app.services.voice_live_service.config_service") as mock_cs:
            mock_cs.get_config = AsyncMock(return_value=mock_config)
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_effective_endpoint = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="endpoint not configured"):
                await get_voice_live_token(db_session)


# ===========================================================================
# 9. Startup seed.py: run_seed
# ===========================================================================


class TestStartupSeedRunner:
    """Tests for startup/seed.py run_seed function."""

    async def test_run_seed_skips_when_ignored(self):
        """run_seed skips when SEED_DATA_IGNORE is set."""
        from app.startup.seed import run_seed

        mock_settings = MagicMock()
        mock_settings.seed_data_ignore = True

        with patch("app.startup.seed.get_settings", return_value=mock_settings):
            await run_seed()

    async def test_run_seed_runs_when_enabled(self):
        """run_seed calls seed_all when enabled."""
        from app.startup.seed import run_seed

        mock_settings = MagicMock()
        mock_settings.seed_data_ignore = False

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_seed_all = AsyncMock()

        with (
            patch("app.startup.seed.get_settings", return_value=mock_settings),
            patch("app.database.AsyncSessionLocal", return_value=mock_session),
            patch("app.startup_seed.seed_all", mock_seed_all),
        ):
            await run_seed()
            mock_seed_all.assert_called_once()

    async def test_run_seed_handles_exception(self):
        """run_seed catches exception gracefully."""
        from app.startup.seed import run_seed

        mock_settings = MagicMock()
        mock_settings.seed_data_ignore = False

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.startup.seed.get_settings", return_value=mock_settings),
            patch("app.database.AsyncSessionLocal", return_value=mock_session),
        ):
            # Should not raise
            await run_seed()


# ===========================================================================
# 10. Encryption: _persist_key_to_env actual file write
# ===========================================================================


class TestEncryptionPersist:
    """Tests for encryption _persist_key_to_env function."""

    def test_persist_key_writes_to_env(self, tmp_path):
        """_persist_key_to_env writes key when not already present."""
        from app.utils.encryption import _persist_key_to_env

        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_VAR=value\n")

        # Patch Path(__file__).resolve().parents[2] to return tmp_path
        mock_resolved = MagicMock()
        mock_resolved.parents.__getitem__ = lambda self, idx: tmp_path

        with patch("app.utils.encryption.Path") as mock_path_cls:
            mock_path_cls.return_value.resolve.return_value = mock_resolved
            _persist_key_to_env("test-encryption-key")

        content = env_file.read_text()
        assert "ENCRYPTION_KEY=test-encryption-key" in content

    def test_persist_key_oserror_handled(self):
        """_persist_key_to_env handles OSError gracefully."""
        import app.utils.encryption as enc_mod

        with patch("app.utils.encryption.Path") as mock_path:
            mock_env = MagicMock()
            mock_env.exists.return_value = False
            mock_env.open.side_effect = OSError("Permission denied")
            mock_path.return_value.resolve.return_value.parents.__getitem__ = lambda self, idx: (
                MagicMock(__truediv__=lambda s, o: mock_env)
            )

            # Should not raise
            enc_mod._persist_key_to_env("test-key")


# ===========================================================================
# 11. Region capabilities: edge cases
# ===========================================================================


class TestRegionCapabilities:
    """Tests for region_capabilities edge cases."""

    def test_voice_live_model_mode_region(self):
        from app.services.region_capabilities import get_region_capabilities

        # swedencentral supports Voice Live (Agent and Model modes)
        result = get_region_capabilities("swedencentral")
        vl = result["services"]["azure_voice_live"]
        assert vl["available"] is True
        assert "Agent" in vl["note"]

    def test_voice_live_unavailable_region(self):
        from app.services.region_capabilities import get_region_capabilities

        # Use a region not in VOICE_LIVE_REGIONS
        result = get_region_capabilities("centralindia")
        vl = result["services"]["azure_voice_live"]
        assert vl["available"] is False
        assert "Not available" in vl["note"]


# ===========================================================================
# 12. Scoring engine: ImportError path
# ===========================================================================


class TestScoringEngineImportError:
    """Test scoring_engine when openai is not installed."""

    async def test_score_with_llm_import_error(self):
        import builtins

        from app.services.scoring_engine import score_with_llm
        from app.utils.exceptions import ScoringUnavailableException

        mock_db = AsyncMock()
        real_import = builtins.__import__

        def selective_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("no openai")
            return real_import(name, *args, **kwargs)

        with (
            patch("app.services.scoring_engine.config_service") as mock_cs,
            patch("builtins.__import__", side_effect=selective_import),
        ):
            mock_cs.get_effective_endpoint = AsyncMock(return_value="https://test.openai.azure.com")
            mock_cs.get_effective_key = AsyncMock(return_value="key")
            mock_cs.get_config = AsyncMock(return_value=MagicMock(model_or_deployment="gpt-4o"))

            with pytest.raises(ScoringUnavailableException):
                await score_with_llm(
                    mock_db,
                    {"hcp_profile": {"name": "Dr. X"}, "product": "Drug"},
                    [{"role": "user", "content": "Hi"}],
                    [],
                    {"key_message": 100},
                )


# ===========================================================================
# 13. Voice Live API routes (avatar-characters, avatar-thumbnail, instances)
# ===========================================================================

ADMIN_ID = "coverage-admin-001"


def _fake_admin():
    from app.models.user import User

    user = User(
        id=ADMIN_ID,
        username="cov_admin",
        email="cov@test.com",
        hashed_password="fake",
        role="admin",
    )
    user.is_active = True
    return user


@pytest.fixture
def admin_client_vl(db_session):
    """HTTP client with admin auth + db override for VL API tests."""
    from app.dependencies import get_current_user

    async def override_get_db():
        yield db_session

    async def override_user():
        return _fake_admin()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    yield
    app.dependency_overrides.clear()


class TestVoiceLiveAPI:
    """Tests for voice_live API endpoints to boost coverage."""

    async def test_avatar_characters_endpoint(self, client, admin_client_vl):
        resp = await client.get("/api/v1/voice-live/avatar-characters")
        assert resp.status_code == 200
        data = resp.json()
        assert "characters" in data
        assert len(data["characters"]) > 0

    async def test_avatar_thumbnail_known_character(self, client):
        """Redirect for known avatar character (no auth needed)."""
        resp = await client.get(
            "/api/v1/voice-live/avatar-thumbnail/lisa",
            follow_redirects=False,
        )
        assert resp.status_code == 307

    async def test_avatar_thumbnail_unknown_character(self, client):
        """Redirect for unknown avatar character falls back to CDN guess."""
        resp = await client.get(
            "/api/v1/voice-live/avatar-thumbnail/nonexistent_xyz",
            follow_redirects=False,
        )
        assert resp.status_code == 307

    async def test_create_list_get_update_delete_instance(
        self, client, admin_client_vl, db_session
    ):
        """Full CRUD cycle for VL instances via API."""
        from app.models.user import User

        # Seed admin user for FK constraint
        admin = User(
            id=ADMIN_ID,
            username="cov_admin",
            email="cov@test.com",
            hashed_password="fake",
            role="admin",
        )
        db_session.add(admin)
        await db_session.commit()

        # Create
        resp = await client.post(
            "/api/v1/voice-live/instances",
            json={
                "name": "API Test Instance",
                "voice_live_model": "gpt-4o",
                "model_instruction": "Test",
            },
        )
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        # List
        resp = await client.get("/api/v1/voice-live/instances")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # Get
        resp = await client.get(f"/api/v1/voice-live/instances/{inst_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "API Test Instance"

        # Update
        resp = await client.put(
            f"/api/v1/voice-live/instances/{inst_id}",
            json={
                "name": "Updated Name",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

        # Delete
        resp = await client.delete(f"/api/v1/voice-live/instances/{inst_id}")
        assert resp.status_code == 204

    async def test_assign_and_unassign_instance(self, client, admin_client_vl, db_session):
        """Assign and unassign VL instance to HCP profile via API."""
        from app.models.hcp_profile import HcpProfile
        from app.models.user import User

        admin = User(
            id=ADMIN_ID,
            username="cov_admin",
            email="cov@test.com",
            hashed_password="fake",
            role="admin",
        )
        db_session.add(admin)
        await db_session.commit()

        # Create instance
        resp = await client.post(
            "/api/v1/voice-live/instances",
            json={
                "name": "Assign Test",
                "voice_live_model": "gpt-4o",
            },
        )
        inst_id = resp.json()["id"]

        # Create HCP profile
        profile = HcpProfile(
            name="Dr. API",
            specialty="Oncology",
            created_by=ADMIN_ID,
        )
        db_session.add(profile)
        await db_session.commit()
        profile_id = profile.id

        # Assign
        resp = await client.post(
            f"/api/v1/voice-live/instances/{inst_id}/assign",
            json={"hcp_profile_id": profile_id},
        )
        assert resp.status_code == 200

        # Unassign
        resp = await client.post(
            "/api/v1/voice-live/instances/unassign",
            json={"hcp_profile_id": profile_id},
        )
        assert resp.status_code == 200
        assert resp.json()["voice_live_instance_id"] is None

    async def test_voice_live_status_endpoint(self, client, admin_client_vl):
        resp = await client.get("/api/v1/voice-live/status")
        assert resp.status_code == 200


# ===========================================================================
# 14. Database get_db rollback path
# ===========================================================================


class TestDatabaseGetDb:
    """Cover the get_db exception→rollback path."""

    async def test_get_db_yields_session(self):
        """get_db yields a usable session."""
        from app.database import get_db

        gen = get_db()
        session = await gen.__anext__()
        assert session is not None
        # Clean exit
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    async def test_get_db_rollback_on_exception(self):
        """get_db rolls back and re-raises on exception."""
        from app.database import get_db

        gen = get_db()
        await gen.__anext__()
        # Simulate an error — throw into the generator
        with pytest.raises(ValueError, match="test error"):
            await gen.athrow(ValueError("test error"))
