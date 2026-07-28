"""Audio transcoding service tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audio_transcoding_service import transcode_audio_to_wav_pcm


@pytest.mark.asyncio
async def test_transcode_audio_to_wav_pcm_uses_ffmpeg():
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b"wav-bytes", b""))
    process.returncode = 0

    with patch(
        "app.services.audio_transcoding_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ) as create_process:
        result = await transcode_audio_to_wav_pcm(b"webm-bytes", timeout_seconds=5)

    assert result == b"wav-bytes"
    args = create_process.await_args.args
    assert args[0] == "ffmpeg"
    assert "16000" in args
    process.communicate.assert_awaited_once_with(b"webm-bytes")


@pytest.mark.asyncio
async def test_transcode_audio_to_wav_pcm_raises_on_ffmpeg_error():
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b"", b"bad input"))
    process.returncode = 1

    with patch(
        "app.services.audio_transcoding_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        with pytest.raises(RuntimeError, match="Audio transcoding failed"):
            await transcode_audio_to_wav_pcm(b"webm-bytes", timeout_seconds=5)


@pytest.mark.asyncio
async def test_transcode_audio_to_wav_pcm_requires_ffmpeg():
    with (
        patch(
            "app.services.audio_transcoding_service.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=FileNotFoundError),
        ),
        pytest.raises(RuntimeError, match="ffmpeg is required"),
    ):
        await transcode_audio_to_wav_pcm(b"webm-bytes")


@pytest.mark.asyncio
async def test_transcode_audio_to_wav_pcm_kills_process_on_timeout():
    process = MagicMock()
    process.communicate = AsyncMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()

    with (
        patch(
            "app.services.audio_transcoding_service.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        patch(
            "app.services.audio_transcoding_service.asyncio.wait_for",
            AsyncMock(side_effect=TimeoutError),
        ),
        pytest.raises(RuntimeError, match="timed out after 3 seconds"),
    ):
        await transcode_audio_to_wav_pcm(b"webm-bytes", timeout_seconds=3)

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcode_audio_to_wav_pcm_rejects_empty_output():
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.returncode = 0

    with (
        patch(
            "app.services.audio_transcoding_service.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        pytest.raises(RuntimeError, match="produced no output"),
    ):
        await transcode_audio_to_wav_pcm(b"webm-bytes")
