"""Speech API: STT transcription and TTS synthesis endpoints."""

import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.speech import SpeechStatusResponse, SynthesizeRequest, TranscribeResponse
from app.services import config_service
from app.services.agents.registry import registry
from app.utils.exceptions import AppException

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["speech"])

STREAM_SAMPLE_RATE = 16000


async def _service_enabled(db: AsyncSession, service_name: str, env_enabled: bool) -> bool:
    """Return true when either deployment flags or admin service config enable a service."""
    if env_enabled:
        return True
    config = await config_service.get_config(db, service_name)
    return bool(config and config.is_active)


async def _ensure_azure_speech_configured(
    db: AsyncSession,
    service_name: str,
    provider: str,
) -> None:
    """Prevent active Azure Speech toggles from silently falling back to mock adapters."""
    if settings.feature_voice_enabled or provider != "mock":
        return

    config = await config_service.get_config(db, service_name)
    if not config or not config.is_active:
        return

    region = await config_service.get_effective_region(db, service_name)
    api_key = await config_service.get_effective_key(db, service_name)
    endpoint = await config_service.get_effective_endpoint(db, service_name)
    if region and (api_key or endpoint):
        return

    raise AppException(
        status_code=503,
        code="AZURE_SPEECH_NOT_CONFIGURED",
        message=(
            "Azure Speech requires a region and either Managed Identity endpoint "
            "configuration or an API key. Configure Azure Speech STT/TTS or provide "
            "a master AI Foundry region."
        ),
    )


async def _authenticate_speech_websocket(ws: WebSocket, db: AsyncSession) -> User | None:
    token = ws.query_params.get("token")
    if not token:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "error", "message": "Authentication required"}))
        await ws.close(code=1008, reason="Authentication required")
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise JWTError("Missing sub claim")
    except JWTError:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "error", "message": "Invalid token"}))
        await ws.close(code=1008, reason="Invalid token")
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "error", "message": "User not found or inactive"}))
        await ws.close(code=1008, reason="User not found or inactive")
        return None

    return user


async def _send_stream_error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_text(json.dumps({"type": "error", "code": code, "message": message}))
    await ws.close(code=1011, reason=code)


@router.get("/status", response_model=SpeechStatusResponse)
async def get_speech_status(
    user: User = Depends(get_current_user),
) -> SpeechStatusResponse:
    """Check STT and TTS service availability."""
    stt_adapter = registry.get("stt", settings.default_stt_provider)
    tts_adapter = registry.get("tts", settings.default_tts_provider)
    stt_available = await stt_adapter.is_available() if stt_adapter else False
    tts_available = await tts_adapter.is_available() if tts_adapter else False
    return SpeechStatusResponse(
        stt_available=stt_available,
        tts_available=tts_available,
        stt_provider=settings.default_stt_provider,
        tts_provider=settings.default_tts_provider,
    )


@router.post("/transcribe", response_model=TranscribeResponse, status_code=200)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Query("zh-CN"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TranscribeResponse:
    """Transcribe uploaded audio to text using the configured STT adapter.

    Accepts audio file via multipart form data.
    Requires feature_voice_enabled to be true.
    """
    if not await _service_enabled(db, "azure_speech_stt", settings.feature_voice_enabled):
        raise AppException(
            status_code=409,
            code="VOICE_NOT_ENABLED",
            message="Voice features are not enabled by the administrator.",
        )

    await _ensure_azure_speech_configured(db, "azure_speech_stt", settings.default_stt_provider)

    stt_adapter = registry.get("stt", settings.default_stt_provider)
    if stt_adapter is None:
        raise AppException(
            status_code=503,
            code="STT_NOT_AVAILABLE",
            message="No STT adapter is available.",
        )

    audio_data = await audio.read()
    if not audio_data:
        raise AppException(
            status_code=422,
            code="EMPTY_AUDIO",
            message="Audio file is empty.",
        )

    try:
        text = await stt_adapter.transcribe(audio_data, language)
    except Exception as exc:
        logger.exception("STT transcription failed: language=%s", language)
        raise AppException(
            status_code=503,
            code="STT_TRANSCRIPTION_FAILED",
            message="Speech transcription failed. Please try again or use text input.",
        ) from exc
    return TranscribeResponse(text=text, language=language)


@router.websocket("/stream")
async def stream_transcription(
    ws: WebSocket,
    language: str = Query("zh-CN"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stream 16 kHz mono PCM audio to Azure Speech continuous recognition."""
    user = await _authenticate_speech_websocket(ws, db)
    if user is None:
        return

    await ws.accept()
    if not await _service_enabled(db, "azure_speech_stt", settings.feature_voice_enabled):
        await _send_stream_error(ws, "VOICE_NOT_ENABLED", "Voice is not enabled")
        return
    try:
        await _ensure_azure_speech_configured(db, "azure_speech_stt", settings.default_stt_provider)
    except AppException as exc:
        await _send_stream_error(ws, exc.code, exc.message)
        return

    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        await _send_stream_error(ws, "STT_NOT_AVAILABLE", "Azure Speech SDK is not installed")
        return

    event_queue: asyncio.Queue[dict[str, str | int]] = asyncio.Queue()
    transcript_parts: list[str] = []
    loop = asyncio.get_running_loop()

    azure_stt_adapter = registry.get("stt", "azure")
    speech_key = getattr(azure_stt_adapter, "_key", settings.azure_speech_key)
    speech_region = getattr(azure_stt_adapter, "_region", settings.azure_speech_region)
    speech_endpoint = getattr(azure_stt_adapter, "_endpoint", "")
    if not speech_region or not (speech_key or speech_endpoint):
        await _send_stream_error(
            ws,
            "AZURE_SPEECH_NOT_CONFIGURED",
            "Azure Speech is not configured",
        )
        return

    if hasattr(azure_stt_adapter, "_create_speech_config"):
        speech_config = azure_stt_adapter._create_speech_config(speechsdk)
    else:
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = language
    stream_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=STREAM_SAMPLE_RATE,
        bits_per_sample=16,
        channels=1,
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    def enqueue(message: dict[str, str | int]) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, message)

    def on_recognizing(evt) -> None:
        text = getattr(evt.result, "text", "")
        if text:
            enqueue({"type": "recognizing", "text": text})

    def on_recognized(evt) -> None:
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text:
            transcript_parts.append(result.text)
            enqueue(
                {
                    "type": "recognized",
                    "text": result.text,
                    "transcript": "".join(transcript_parts),
                }
            )

    def on_canceled(evt) -> None:
        details = getattr(evt, "cancellation_details", None)
        message = getattr(details, "error_details", "Speech recognition canceled")
        enqueue({"type": "error", "code": "STT_STREAM_CANCELED", "message": message})

    recognizer.recognizing.connect(on_recognizing)
    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)

    disconnected = False

    async def send_events() -> None:
        while True:
            message = await event_queue.get()
            await ws.send_text(json.dumps(message, ensure_ascii=False))
            if message.get("type") in {"done", "error"}:
                return

    sender_task = asyncio.create_task(send_events())
    try:
        await asyncio.to_thread(recognizer.start_continuous_recognition_async().get)
        await ws.send_text(
            json.dumps({"type": "ready", "sampleRate": STREAM_SAMPLE_RATE, "language": language})
        )
        while True:
            message = await ws.receive()
            if audio_bytes := message.get("bytes"):
                push_stream.write(audio_bytes)
                continue
            text_message = message.get("text")
            if text_message:
                try:
                    payload = json.loads(text_message)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "stop":
                    break
            if message.get("type") == "websocket.disconnect":
                disconnected = True
                break
    except WebSocketDisconnect:
        disconnected = True
    except Exception:
        logger.exception("Streaming STT failed for user=%s language=%s", user.id, language)
        if not disconnected:
            enqueue(
                {
                    "type": "error",
                    "code": "STT_STREAM_FAILED",
                    "message": "Speech transcription failed",
                }
            )
    finally:
        push_stream.close()
        await asyncio.to_thread(recognizer.stop_continuous_recognition_async().get)
        if not disconnected and not sender_task.done():
            enqueue({"type": "done", "text": "".join(transcript_parts)})
            await sender_task
            await ws.close()
        elif not sender_task.done():
            sender_task.cancel()


@router.post("/synthesize", status_code=200)
async def synthesize_speech(
    request: SynthesizeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Synthesize text to speech audio using the configured TTS adapter.

    Returns audio bytes with audio/wav content type.
    Requires feature_voice_enabled to be true.
    """
    if not await _service_enabled(db, "azure_speech_tts", settings.feature_voice_enabled):
        raise AppException(
            status_code=409,
            code="VOICE_NOT_ENABLED",
            message="Voice features are not enabled by the administrator.",
        )

    await _ensure_azure_speech_configured(db, "azure_speech_tts", settings.default_tts_provider)

    tts_adapter = registry.get("tts", settings.default_tts_provider)
    if tts_adapter is None:
        raise AppException(
            status_code=503,
            code="TTS_NOT_AVAILABLE",
            message="No TTS adapter is available.",
        )

    if not request.text.strip():
        raise AppException(
            status_code=422,
            code="EMPTY_TEXT",
            message="Text to synthesize is empty.",
        )

    audio_bytes = await tts_adapter.synthesize(request.text, request.language, request.voice)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=speech.wav"},
    )
