"""Azure Speech-to-Text adapter using Cognitive Services SDK."""

import asyncio
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from app.services.agents.stt.base import BaseSTTAdapter
from app.services.azure_auth import get_token_credential_sync

logger = logging.getLogger(__name__)


class AzureSTTAdapter(BaseSTTAdapter):
    """Azure Speech-to-Text adapter wrapping the Cognitive Services SDK.

    Uses asyncio.to_thread() to avoid blocking the event loop since the
    Azure Speech SDK is synchronous by default (per RESEARCH Pitfall 2).
    """

    name = "azure"

    def __init__(self, key: str, region: str, endpoint: str = "") -> None:
        self._key = key
        self._region = region
        self._endpoint = _normalize_speech_endpoint(endpoint)

    async def transcribe(self, audio_data: bytes, language: str = "zh-CN") -> str:
        """Transcribe audio bytes to text using Azure Speech SDK.

        Uses PushAudioInputStream and recognize_once wrapped in asyncio.to_thread.
        """
        rest_result = await self._transcribe_pcm_wav_with_rest(audio_data, language)
        if rest_result is not None:
            return rest_result

        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise RuntimeError(
                "azure-cognitiveservices-speech not installed. "
                "Install with: pip install 'azure-cognitiveservices-speech>=1.48.0'"
            ) from None

        speech_config = self._create_speech_config(speechsdk)
        speech_config.speech_recognition_language = language

        audio_config, cleanup_path = _audio_config_from_bytes(speechsdk, audio_data)

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )

        # Use asyncio.to_thread to avoid blocking event loop
        try:
            result = await asyncio.to_thread(recognizer.recognize_once)
        finally:
            if cleanup_path is not None:
                try:
                    cleanup_path.unlink(missing_ok=True)
                except PermissionError:
                    logger.debug("Temporary STT audio file still in use: %s", cleanup_path)

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return ""
        else:
            raise RuntimeError(f"STT error: {result.reason}")

    async def is_available(self) -> bool:
        """Check if Azure Speech can be addressed with key or Entra auth."""
        return bool(self._region and (self._key or self._endpoint))

    def _create_speech_config(self, speechsdk):
        """Create SpeechConfig with API key fallback after Entra token credential."""
        if self._key:
            return speechsdk.SpeechConfig(subscription=self._key, region=self._region)

        credential = get_token_credential_sync()
        if credential is not None and self._endpoint:
            return speechsdk.SpeechConfig(token_credential=credential, endpoint=self._endpoint)

        raise RuntimeError("Azure Speech requires Managed Identity with an endpoint or an API key.")

    async def _transcribe_pcm_wav_with_rest(
        self,
        audio_data: bytes,
        language: str,
    ) -> str | None:
        sample_rate = _pcm_wav_sample_rate(audio_data)
        if sample_rate is None:
            return None

        if not self._key:
            return None

        url = (
            f"https://{self._region}.stt.speech.microsoft.com/"
            "speech/recognition/conversation/cognitiveservices/v1"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={sample_rate}",
            "Accept": "application/json",
        }
        params = {"language": language}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    headers=headers,
                    content=audio_data,
                )
            if response.status_code >= 400:
                logger.debug(
                    "Azure Speech REST STT returned HTTP %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None
            payload = response.json()
        except Exception as exc:
            logger.debug("Azure Speech REST STT failed, falling back to SDK: %s", exc)
            return None

        status = payload.get("RecognitionStatus")
        if status == "Success":
            return payload.get("DisplayText", "")
        if status in {"NoMatch", "InitialSilenceTimeout", "BabbleTimeout"}:
            return ""
        logger.debug("Azure Speech REST STT returned status %s: %s", status, payload)
        return None


def _audio_config_from_bytes(speechsdk, audio_data: bytes):
    if audio_data.startswith(b"RIFF") and audio_data[8:12] == b"WAVE":
        temp_file = NamedTemporaryFile(suffix=".wav", delete=False)
        temp_file.write(audio_data)
        temp_file.close()
        path = Path(temp_file.name)
        return speechsdk.audio.AudioConfig(filename=str(path)), path

    push_stream = speechsdk.audio.PushAudioInputStream()
    push_stream.write(audio_data)
    push_stream.close()
    return speechsdk.audio.AudioConfig(stream=push_stream), None


def _pcm_wav_sample_rate(audio_data: bytes) -> int | None:
    if len(audio_data) < 44:
        return None
    if not (audio_data.startswith(b"RIFF") and audio_data[8:12] == b"WAVE"):
        return None
    audio_format = int.from_bytes(audio_data[20:22], "little")
    sample_rate = int.from_bytes(audio_data[24:28], "little")
    bits_per_sample = int.from_bytes(audio_data[34:36], "little")
    if audio_format != 1 or sample_rate <= 0 or bits_per_sample != 16:
        return None
    return sample_rate


def _normalize_speech_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith(".services.ai.azure.com"):
        endpoint = endpoint.removesuffix(".services.ai.azure.com") + ".cognitiveservices.azure.com"
    return endpoint + "/"
