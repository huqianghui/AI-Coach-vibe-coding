"""Azure Text-to-Speech adapter using Cognitive Services SDK."""

import asyncio

from app.services.agents.stt.azure import _normalize_speech_endpoint
from app.services.agents.tts.base import BaseTTSAdapter
from app.services.azure_auth import get_token_credential_sync


class AzureTTSAdapter(BaseTTSAdapter):
    """Azure Text-to-Speech adapter wrapping the Cognitive Services SDK.

    Uses SSML for voice selection and asyncio.to_thread() to avoid blocking
    the event loop (per RESEARCH Pitfall 2).
    """

    name = "azure"

    def __init__(self, key: str, region: str, endpoint: str = "") -> None:
        self._key = key
        self._region = region
        self._endpoint = _normalize_speech_endpoint(endpoint)

    async def synthesize(
        self, text: str, language: str = "zh-CN", voice: str | None = None
    ) -> bytes:
        """Convert text to audio bytes using Azure Speech SDK.

        Uses SSML for voice selection and outputs to an in-memory audio stream.
        """
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise RuntimeError(
                "azure-cognitiveservices-speech not installed. "
                "Install with: pip install 'azure-cognitiveservices-speech>=1.48.0'"
            ) from None

        voice_id = voice or "zh-CN-XiaoxiaoNeural"

        speech_config = self._create_speech_config(speechsdk)

        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        # Build SSML for voice selection
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{language}">'
            f'<voice name="{voice_id}">{_escape_xml(text)}</voice>'
            "</speak>"
        )

        # Use asyncio.to_thread to avoid blocking event loop
        result = await asyncio.to_thread(synthesizer.speak_ssml, ssml)

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return result.audio_data
        else:
            cancellation = result.cancellation_details
            raise RuntimeError(f"TTS error: {cancellation.reason} - {cancellation.error_details}")

    async def list_voices(self, language: str = "zh-CN") -> list[dict]:
        """Return curated list of 6 zh-CN Azure Neural voices for conference HCPs.

        Each entry maps to a distinct voice for speaker diversity in multi-HCP sessions.
        """
        zh_cn_voices = [
            {
                "voice_id": "zh-CN-XiaoxiaoNeural",
                "display_name": "Xiaoxiao (Female)",
                "gender": "female",
                "language": "zh-CN",
            },
            {
                "voice_id": "zh-CN-YunxiNeural",
                "display_name": "Yunxi (Male)",
                "gender": "male",
                "language": "zh-CN",
            },
            {
                "voice_id": "zh-CN-XiaoyiNeural",
                "display_name": "Xiaoyi (Female)",
                "gender": "female",
                "language": "zh-CN",
            },
            {
                "voice_id": "zh-CN-YunjianNeural",
                "display_name": "Yunjian (Male)",
                "gender": "male",
                "language": "zh-CN",
            },
            {
                "voice_id": "zh-CN-XiaochenNeural",
                "display_name": "Xiaochen (Female)",
                "gender": "female",
                "language": "zh-CN",
            },
            {
                "voice_id": "zh-CN-YunzeNeural",
                "display_name": "Yunze (Male)",
                "gender": "male",
                "language": "zh-CN",
            },
        ]

        en_us_voices = [
            {
                "voice_id": "en-US-JennyNeural",
                "display_name": "Jenny (Female)",
                "gender": "female",
                "language": "en-US",
            },
            {
                "voice_id": "en-US-GuyNeural",
                "display_name": "Guy (Male)",
                "gender": "male",
                "language": "en-US",
            },
            {
                "voice_id": "en-US-AriaNeural",
                "display_name": "Aria (Female)",
                "gender": "female",
                "language": "en-US",
            },
            {
                "voice_id": "en-US-DavisNeural",
                "display_name": "Davis (Male)",
                "gender": "male",
                "language": "en-US",
            },
        ]

        if language.startswith("en"):
            return en_us_voices
        return zh_cn_voices

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


def _escape_xml(text: str) -> str:
    """Escape special XML characters for SSML content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
