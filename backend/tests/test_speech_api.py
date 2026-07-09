"""Speech API endpoint tests: STT transcription, TTS synthesis, and status check.

Covers all branches of backend/app/api/speech.py including:
- Authentication (401)
- Feature flag gating (409 VOICE_NOT_ENABLED)
- Adapter not available (503)
- Empty input validation (422)
- Happy paths for status, transcribe, and synthesize
"""

from io import BytesIO
from unittest.mock import AsyncMock, patch

from app.models.service_config import ServiceConfig
from app.models.user import User
from app.services.auth import create_access_token, get_password_hash
from tests.conftest import TestSessionLocal


async def _create_user_and_token(username="speech_user") -> tuple[str, str]:
    """Create a regular user and return (user_id, bearer_token)."""
    async with TestSessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("pass"),
            full_name="Speech User",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(data={"sub": user.id})
        return user.id, token


class TestSpeechStatus:
    """Tests for GET /api/v1/speech/status."""

    async def test_status_unauthenticated(self, client):
        """GET /api/v1/speech/status returns 401 without auth."""
        response = await client.get("/api/v1/speech/status")
        assert response.status_code == 401

    async def test_status_returns_availability(self, client):
        """GET /api/v1/speech/status returns STT/TTS availability."""
        _, token = await _create_user_and_token("speech_status")
        response = await client.get(
            "/api/v1/speech/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "stt_available" in data
        assert "tts_available" in data
        assert "stt_provider" in data
        assert "tts_provider" in data


class TestTranscribeAudio:
    """Tests for POST /api/v1/speech/transcribe."""

    async def test_transcribe_unauthenticated(self, client):
        """POST /api/v1/speech/transcribe returns 401 without auth."""
        response = await client.post("/api/v1/speech/transcribe")
        assert response.status_code == 401

    @patch("app.api.speech.settings")
    async def test_transcribe_voice_not_enabled(self, mock_settings, client):
        """POST /api/v1/speech/transcribe returns 409 when voice disabled."""
        mock_settings.feature_voice_enabled = False
        _, token = await _create_user_and_token("speech_trans_disabled")
        audio_data = BytesIO(b"fake audio data")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "VOICE_NOT_ENABLED"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_stt_not_available(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/transcribe returns 503 when no STT adapter."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_stt_provider = "mock"
        mock_registry.get.return_value = None
        _, token = await _create_user_and_token("speech_trans_no_stt")
        audio_data = BytesIO(b"fake audio data")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "STT_NOT_AVAILABLE"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_empty_audio(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/transcribe returns 422 for empty audio."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_stt_provider = "mock"
        mock_adapter = AsyncMock()
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_trans_empty")
        audio_data = BytesIO(b"")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "EMPTY_AUDIO"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_happy_path(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/transcribe returns transcribed text."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_stt_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(return_value="你好医生")
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_trans_ok")
        audio_data = BytesIO(b"fake audio bytes here")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
            data={"language": "zh-CN"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "你好医生"
        assert data["language"] == "zh-CN"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_rejects_active_stt_config_without_credentials(
        self, mock_settings, mock_registry, client
    ):
        """Active Azure Speech STT config must not silently fall back to mock."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_stt_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(return_value="会议发言")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_stt",
                    display_name="Azure Speech (STT)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_trans_active_config")
        audio_data = BytesIO(b"fake audio bytes here")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
        )

        assert response.status_code == 503
        assert response.json()["code"] == "AZURE_SPEECH_NOT_CONFIGURED"
        mock_adapter.transcribe.assert_not_awaited()

    @patch("app.api.speech.config_service.get_effective_region", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_endpoint", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_key", new_callable=AsyncMock)
    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_allows_active_stt_config_with_master_credentials(
        self,
        mock_settings,
        mock_registry,
        mock_get_effective_key,
        mock_get_effective_endpoint,
        mock_get_effective_region,
        client,
    ):
        """Active Azure Speech STT can use effective master credentials."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_stt_provider = "azure"
        mock_get_effective_key.return_value = "master-speech-key"
        mock_get_effective_endpoint.return_value = ""
        mock_get_effective_region.return_value = "eastus"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(return_value="会议发言")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_stt",
                    display_name="Azure Speech (STT)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_trans_master_config")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", BytesIO(b"fake audio bytes here"), "audio/wav")},
        )

        assert response.status_code == 200
        assert response.json()["text"] == "会议发言"
        mock_adapter.transcribe.assert_awaited_once()

    @patch("app.api.speech.config_service.get_effective_region", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_endpoint", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_key", new_callable=AsyncMock)
    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_allows_active_stt_config_with_entra_endpoint(
        self,
        mock_settings,
        mock_registry,
        mock_get_effective_key,
        mock_get_effective_endpoint,
        mock_get_effective_region,
        client,
    ):
        """Active Azure Speech STT can use endpoint and region without an API key."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_stt_provider = "mock"
        mock_get_effective_key.return_value = ""
        mock_get_effective_endpoint.return_value = "https://speech.cognitiveservices.azure.com/"
        mock_get_effective_region.return_value = "eastus"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(return_value="会议发言")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_stt",
                    display_name="Azure Speech (STT)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_trans_entra_config")
        response = await client.post(
            "/api/v1/speech/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", BytesIO(b"fake audio bytes here"), "audio/wav")},
        )

        assert response.status_code == 200
        assert response.json()["text"] == "会议发言"
        mock_adapter.transcribe.assert_awaited_once()

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_custom_language(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/transcribe supports custom language parameter."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_stt_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(return_value="Hello doctor")
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_trans_en")
        audio_data = BytesIO(b"english audio")
        response = await client.post(
            "/api/v1/speech/transcribe?language=en-US",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", audio_data, "audio/wav")},
        )
        assert response.status_code == 200
        assert response.json()["language"] == "en-US"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_transcribe_adapter_failure_returns_503(
        self, mock_settings, mock_registry, client
    ):
        """POST /api/v1/speech/transcribe maps STT adapter errors to 503."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_stt_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.transcribe = AsyncMock(side_effect=RuntimeError("decoder failed"))
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_trans_adapter_error")
        response = await client.post(
            "/api/v1/speech/transcribe?language=zh-CN",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", BytesIO(b"fake audio"), "audio/wav")},
        )

        assert response.status_code == 503
        assert response.json()["code"] == "STT_TRANSCRIPTION_FAILED"


class TestSynthesizeSpeech:
    """Tests for POST /api/v1/speech/synthesize."""

    async def test_synthesize_unauthenticated(self, client):
        """POST /api/v1/speech/synthesize returns 401 without auth."""
        response = await client.post(
            "/api/v1/speech/synthesize",
            json={"text": "hello"},
        )
        assert response.status_code == 401

    @patch("app.api.speech.settings")
    async def test_synthesize_voice_not_enabled(self, mock_settings, client):
        """POST /api/v1/speech/synthesize returns 409 when voice disabled."""
        mock_settings.feature_voice_enabled = False
        _, token = await _create_user_and_token("speech_synth_disabled")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello doctor"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "VOICE_NOT_ENABLED"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_tts_not_available(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/synthesize returns 503 when no TTS adapter."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_tts_provider = "mock"
        mock_registry.get.return_value = None
        _, token = await _create_user_and_token("speech_synth_no_tts")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello doctor"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "TTS_NOT_AVAILABLE"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_empty_text(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/synthesize returns 422 for empty text."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_tts_provider = "mock"
        mock_adapter = AsyncMock()
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_synth_empty")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "   "},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "EMPTY_TEXT"

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_happy_path(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/synthesize returns audio/wav bytes."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_tts_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.synthesize = AsyncMock(return_value=b"RIFF\x00\x00audio")
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_synth_ok")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "你好", "language": "zh-CN"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_with_voice_param(self, mock_settings, mock_registry, client):
        """POST /api/v1/speech/synthesize passes voice parameter to adapter."""
        mock_settings.feature_voice_enabled = True
        mock_settings.default_tts_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.synthesize = AsyncMock(return_value=b"audio data")
        mock_registry.get.return_value = mock_adapter
        _, token = await _create_user_and_token("speech_synth_voice")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello", "language": "en-US", "voice": "en-US-JennyNeural"},
        )
        assert response.status_code == 200
        mock_adapter.synthesize.assert_called_once_with("Hello", "en-US", "en-US-JennyNeural")

    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_rejects_active_tts_config_without_credentials(
        self, mock_settings, mock_registry, client
    ):
        """Active Azure Speech TTS config must not silently fall back to mock."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_tts_provider = "mock"
        mock_adapter = AsyncMock()
        mock_adapter.synthesize = AsyncMock(return_value=b"audio data")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_tts",
                    display_name="Azure Speech (TTS)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_synth_active_config_no_key")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello"},
        )

        assert response.status_code == 503
        assert response.json()["code"] == "AZURE_SPEECH_NOT_CONFIGURED"
        mock_adapter.synthesize.assert_not_awaited()

    @patch("app.api.speech.config_service.get_effective_region", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_endpoint", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_key", new_callable=AsyncMock)
    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_allows_active_tts_config_with_master_credentials(
        self,
        mock_settings,
        mock_registry,
        mock_get_effective_key,
        mock_get_effective_endpoint,
        mock_get_effective_region,
        client,
    ):
        """Active Azure Speech TTS can use effective master credentials."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_tts_provider = "azure"
        mock_get_effective_key.return_value = "master-speech-key"
        mock_get_effective_endpoint.return_value = ""
        mock_get_effective_region.return_value = "eastus"
        mock_adapter = AsyncMock()
        mock_adapter.synthesize = AsyncMock(return_value=b"audio data")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_tts",
                    display_name="Azure Speech (TTS)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_synth_master_config")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello"},
        )

        assert response.status_code == 200
        assert response.content == b"audio data"
        mock_adapter.synthesize.assert_awaited_once()

    @patch("app.api.speech.config_service.get_effective_region", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_endpoint", new_callable=AsyncMock)
    @patch("app.api.speech.config_service.get_effective_key", new_callable=AsyncMock)
    @patch("app.api.speech.registry")
    @patch("app.api.speech.settings")
    async def test_synthesize_allows_active_tts_config_with_entra_endpoint(
        self,
        mock_settings,
        mock_registry,
        mock_get_effective_key,
        mock_get_effective_endpoint,
        mock_get_effective_region,
        client,
    ):
        """Active Azure Speech TTS can use endpoint and region without an API key."""
        mock_settings.feature_voice_enabled = False
        mock_settings.default_tts_provider = "mock"
        mock_get_effective_key.return_value = ""
        mock_get_effective_endpoint.return_value = "https://speech.cognitiveservices.azure.com/"
        mock_get_effective_region.return_value = "eastus"
        mock_adapter = AsyncMock()
        mock_adapter.synthesize = AsyncMock(return_value=b"audio data")
        mock_registry.get.return_value = mock_adapter
        async with TestSessionLocal() as session:
            session.add(
                ServiceConfig(
                    service_name="azure_speech_tts",
                    display_name="Azure Speech (TTS)",
                    is_active=True,
                )
            )
            await session.commit()

        _, token = await _create_user_and_token("speech_synth_entra_config")
        response = await client.post(
            "/api/v1/speech/synthesize",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "Hello"},
        )

        assert response.status_code == 200
        assert response.content == b"audio data"
        mock_adapter.synthesize.assert_awaited_once()


class TestSpeechSchemas:
    """Tests for speech request/response Pydantic schemas."""

    async def test_transcribe_response_schema(self):
        from app.schemas.speech import TranscribeResponse

        resp = TranscribeResponse(text="hello", language="en-US")
        assert resp.text == "hello"
        assert resp.language == "en-US"

    async def test_synthesize_request_defaults(self):
        from app.schemas.speech import SynthesizeRequest

        req = SynthesizeRequest(text="hello")
        assert req.language == "zh-CN"
        assert req.voice is None

    async def test_synthesize_request_with_voice(self):
        from app.schemas.speech import SynthesizeRequest

        req = SynthesizeRequest(text="hi", language="en-US", voice="en-US-JennyNeural")
        assert req.voice == "en-US-JennyNeural"

    async def test_speech_status_response_schema(self):
        from app.schemas.speech import SpeechStatusResponse

        resp = SpeechStatusResponse(
            stt_available=True,
            tts_available=False,
            stt_provider="mock",
            tts_provider="mock",
        )
        assert resp.stt_available is True
        assert resp.tts_available is False
