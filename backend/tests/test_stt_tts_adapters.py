"""Tests for Azure STT and TTS adapters: availability, voice listing, SDK handling."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.services.agents.stt.azure import AzureSTTAdapter
from app.services.agents.tts.azure import AzureTTSAdapter, _escape_xml


def _mock_azure_speech_sdk():
    """Create a complete mock of the azure.cognitiveservices.speech SDK.

    Returns (sdk_mock, modules_dict) where modules_dict can be passed
    to patch.dict('sys.modules', ...) to fake the entire package chain.
    The package hierarchy is wired so azure.cognitiveservices.speech
    always resolves to the same sdk mock object.
    """
    sdk = MagicMock()
    azure_cs = MagicMock()
    azure_cs.speech = sdk
    azure_mod = MagicMock()
    azure_mod.cognitiveservices = azure_cs
    azure_mod.cognitiveservices.speech = sdk
    modules = {
        "azure": azure_mod,
        "azure.cognitiveservices": azure_cs,
        "azure.cognitiveservices.speech": sdk,
    }
    return sdk, modules


class TestAzureSTTAvailability:
    """Tests for AzureSTTAdapter.is_available."""

    async def test_unavailable_without_credentials(self):
        """Empty key/region makes adapter unavailable."""
        adapter = AzureSTTAdapter("", "")
        assert await adapter.is_available() is False

    async def test_unavailable_with_empty_key(self):
        """Empty key with valid region but no endpoint is unavailable."""
        adapter = AzureSTTAdapter("", "eastus")
        assert await adapter.is_available() is False

    async def test_unavailable_with_empty_region(self):
        """Valid key with empty region is still unavailable."""
        adapter = AzureSTTAdapter("some-key", "")
        assert await adapter.is_available() is False

    async def test_available_with_credentials(self):
        """Both key and region provided makes adapter available."""
        adapter = AzureSTTAdapter("my-key", "eastus")
        assert await adapter.is_available() is True

    async def test_available_with_entra_endpoint_and_region(self):
        """Endpoint plus region allows keyless Managed Identity auth."""
        adapter = AzureSTTAdapter("", "eastus", "https://speech.cognitiveservices.azure.com/")
        assert await adapter.is_available() is True


class TestAzureSTTTranscribe:
    """Tests for AzureSTTAdapter.transcribe error handling."""

    async def test_transcribe_without_sdk_raises_runtime_error(self):
        """Transcribe raises RuntimeError when azure SDK is not installed."""
        adapter = AzureSTTAdapter("key", "region")
        with patch.dict("sys.modules", {"azure.cognitiveservices.speech": None}):
            with pytest.raises(RuntimeError, match="azure-cognitiveservices-speech"):
                await adapter.transcribe(b"fake-audio")

    async def test_adapter_name(self):
        """Adapter name is 'azure'."""
        adapter = AzureSTTAdapter("k", "r")
        assert adapter.name == "azure"

    async def test_keyless_config_uses_token_credential_endpoint(self):
        """Keyless STT creates SpeechConfig with TokenCredential and custom endpoint."""
        sdk, _ = _mock_azure_speech_sdk()
        credential = MagicMock()
        adapter = AzureSTTAdapter("", "eastus", "https://speech.services.ai.azure.com")

        with patch(
            "app.services.agents.stt.azure.get_token_credential_sync",
            return_value=credential,
        ):
            adapter._create_speech_config(sdk)

        sdk.SpeechConfig.assert_called_once_with(
            token_credential=credential,
            endpoint="https://speech.cognitiveservices.azure.com/",
        )

    async def test_transcribe_recognized_speech(self):
        """Transcribe returns text when speech is recognized."""
        sdk, modules = _mock_azure_speech_sdk()
        # Use a real sentinel for comparison
        recognized = object()
        no_match = object()
        sdk.ResultReason.RecognizedSpeech = recognized
        sdk.ResultReason.NoMatch = no_match

        mock_result = MagicMock()
        mock_result.reason = recognized  # match RecognizedSpeech
        mock_result.text = "Hello world"

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_once.return_value = mock_result
        sdk.SpeechRecognizer.return_value = mock_recognizer

        adapter = AzureSTTAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            text = await adapter.transcribe(b"fake-audio")
        assert text == "Hello world"
        sdk.audio.AudioConfig.assert_called_once()
        assert "stream" in sdk.audio.AudioConfig.call_args.kwargs

    async def test_transcribe_wav_uses_file_audio_config(self):
        """WAV input is passed to Azure via filename instead of raw push stream."""
        sdk, modules = _mock_azure_speech_sdk()
        recognized = object()
        sdk.ResultReason.RecognizedSpeech = recognized
        sdk.ResultReason.NoMatch = object()

        mock_result = MagicMock()
        mock_result.reason = recognized
        mock_result.text = "会议发言"

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_once.return_value = mock_result
        sdk.SpeechRecognizer.return_value = mock_recognizer

        adapter = AzureSTTAdapter("key", "region")
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
        with patch.dict(sys.modules, modules):
            text = await adapter.transcribe(wav_bytes)

        assert text == "会议发言"
        sdk.audio.PushAudioInputStream.assert_not_called()
        assert "filename" in sdk.audio.AudioConfig.call_args.kwargs

    async def test_transcribe_no_match(self):
        """Transcribe returns empty string when no speech detected."""
        sdk, modules = _mock_azure_speech_sdk()
        recognized = object()
        no_match = object()
        sdk.ResultReason.RecognizedSpeech = recognized
        sdk.ResultReason.NoMatch = no_match

        mock_result = MagicMock()
        mock_result.reason = no_match

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_once.return_value = mock_result
        sdk.SpeechRecognizer.return_value = mock_recognizer

        adapter = AzureSTTAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            text = await adapter.transcribe(b"silence")
        assert text == ""

    async def test_transcribe_error(self):
        """Transcribe raises RuntimeError on STT error."""
        sdk, modules = _mock_azure_speech_sdk()
        recognized = object()
        no_match = object()
        sdk.ResultReason.RecognizedSpeech = recognized
        sdk.ResultReason.NoMatch = no_match

        mock_result = MagicMock()
        mock_result.reason = object()  # something else

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_once.return_value = mock_result
        sdk.SpeechRecognizer.return_value = mock_recognizer

        adapter = AzureSTTAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            with pytest.raises(RuntimeError, match="STT error"):
                await adapter.transcribe(b"bad-audio")


class TestAzureTTSAvailability:
    """Tests for AzureTTSAdapter.is_available."""

    async def test_unavailable_without_credentials(self):
        """Empty key/region makes adapter unavailable."""
        adapter = AzureTTSAdapter("", "")
        assert await adapter.is_available() is False

    async def test_unavailable_with_empty_key(self):
        """Empty key with valid region but no endpoint is unavailable."""
        adapter = AzureTTSAdapter("", "eastus")
        assert await adapter.is_available() is False

    async def test_available_with_credentials(self):
        """Both key and region provided makes adapter available."""
        adapter = AzureTTSAdapter("my-key", "eastus")
        assert await adapter.is_available() is True

    async def test_available_with_entra_endpoint_and_region(self):
        """Endpoint plus region allows keyless Managed Identity auth."""
        adapter = AzureTTSAdapter("", "eastus", "https://speech.cognitiveservices.azure.com/")
        assert await adapter.is_available() is True


class TestAzureTTSListVoices:
    """Tests for AzureTTSAdapter.list_voices."""

    async def test_zh_cn_voices(self):
        """Returns zh-CN voices by default."""
        adapter = AzureTTSAdapter("key", "region")
        voices = await adapter.list_voices("zh-CN")
        assert len(voices) == 6
        for v in voices:
            assert "voice_id" in v
            assert "display_name" in v
            assert "gender" in v
            assert "language" in v
            assert v["language"] == "zh-CN"

    async def test_en_us_voices(self):
        """Returns en-US voices for English language."""
        adapter = AzureTTSAdapter("key", "region")
        voices = await adapter.list_voices("en-US")
        assert len(voices) == 4
        for v in voices:
            assert v["language"] == "en-US"

    async def test_default_language_is_zh_cn(self):
        """Default language parameter returns zh-CN voices."""
        adapter = AzureTTSAdapter("key", "region")
        voices = await adapter.list_voices()
        assert all(v["language"] == "zh-CN" for v in voices)


class TestAzureTTSSynthesize:
    """Tests for AzureTTSAdapter.synthesize error handling."""

    async def test_keyless_config_uses_token_credential_endpoint(self):
        """Keyless TTS creates SpeechConfig with TokenCredential and custom endpoint."""
        sdk, _ = _mock_azure_speech_sdk()
        credential = MagicMock()
        adapter = AzureTTSAdapter("", "eastus", "https://speech.services.ai.azure.com")

        with patch(
            "app.services.agents.tts.azure.get_token_credential_sync",
            return_value=credential,
        ):
            adapter._create_speech_config(sdk)

        sdk.SpeechConfig.assert_called_once_with(
            token_credential=credential,
            endpoint="https://speech.cognitiveservices.azure.com/",
        )

    async def test_synthesize_without_sdk_raises_runtime_error(self):
        """Synthesize raises RuntimeError when azure SDK is not installed."""
        adapter = AzureTTSAdapter("key", "region")
        with patch.dict("sys.modules", {"azure.cognitiveservices.speech": None}):
            with pytest.raises(RuntimeError, match="azure-cognitiveservices-speech"):
                await adapter.synthesize("Hello world")

    async def test_adapter_name(self):
        """Adapter name is 'azure'."""
        adapter = AzureTTSAdapter("k", "r")
        assert adapter.name == "azure"

    async def test_synthesize_success(self):
        """Synthesize returns audio bytes on success."""
        sdk, modules = _mock_azure_speech_sdk()
        completed = object()
        sdk.ResultReason.SynthesizingAudioCompleted = completed

        mock_result = MagicMock()
        mock_result.reason = completed
        mock_result.audio_data = b"audio-bytes"

        mock_synth = MagicMock()
        mock_synth.speak_ssml.return_value = mock_result
        sdk.SpeechSynthesizer.return_value = mock_synth

        adapter = AzureTTSAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            audio = await adapter.synthesize("Hello")
        assert audio == b"audio-bytes"

    async def test_synthesize_error(self):
        """Synthesize raises RuntimeError on TTS error."""
        sdk, modules = _mock_azure_speech_sdk()
        completed = object()
        sdk.ResultReason.SynthesizingAudioCompleted = completed

        mock_result = MagicMock()
        mock_result.reason = object()  # not completed
        mock_result.cancellation_details.reason = "Error"
        mock_result.cancellation_details.error_details = "Bad request"

        mock_synth = MagicMock()
        mock_synth.speak_ssml.return_value = mock_result
        sdk.SpeechSynthesizer.return_value = mock_synth

        adapter = AzureTTSAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            with pytest.raises(RuntimeError, match="TTS error"):
                await adapter.synthesize("Hello")

    async def test_synthesize_custom_voice(self):
        """Synthesize uses custom voice_id when provided."""
        sdk, modules = _mock_azure_speech_sdk()
        completed = object()
        sdk.ResultReason.SynthesizingAudioCompleted = completed

        mock_result = MagicMock()
        mock_result.reason = completed
        mock_result.audio_data = b"audio"

        mock_synth = MagicMock()
        mock_synth.speak_ssml.return_value = mock_result
        sdk.SpeechSynthesizer.return_value = mock_synth

        adapter = AzureTTSAdapter("key", "region")
        with patch.dict(sys.modules, modules):
            await adapter.synthesize("Hello", voice="en-US-JennyNeural")
        call_args = mock_synth.speak_ssml.call_args[0][0]
        assert "en-US-JennyNeural" in call_args


class TestEscapeXml:
    """Tests for the _escape_xml helper function."""

    def test_escapes_ampersand(self):
        assert _escape_xml("A & B") == "A &amp; B"

    def test_escapes_lt_gt(self):
        assert _escape_xml("<tag>") == "&lt;tag&gt;"

    def test_escapes_quotes(self):
        assert _escape_xml('say "hello"') == "say &quot;hello&quot;"

    def test_escapes_apostrophe(self):
        assert _escape_xml("it's") == "it&apos;s"

    def test_no_escape_needed(self):
        assert _escape_xml("hello world") == "hello world"

    def test_multiple_special_chars(self):
        result = _escape_xml('<a href="x">&</a>')
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result
