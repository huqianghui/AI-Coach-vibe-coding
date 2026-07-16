"""Voice Live API: WebSocket proxy, token broker, instance CRUD, and config endpoints."""

import json
import logging
import time

from fastapi import APIRouter, Depends, Query, WebSocket
from fastapi.responses import Response
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.voice_live import (
    AvatarCharacterInfo,
    AvatarCharactersResponse,
    AvatarCharacterStyle,
    VoiceLiveConfigStatus,
    VoiceLiveModelInfo,
    VoiceLiveModelsResponse,
    VoiceLiveTokenResponse,
    WebRTCSessionResponse,
)
from app.schemas.voice_live_instance import (
    VoiceLiveInstanceAssign,
    VoiceLiveInstanceCreate,
    VoiceLiveInstanceListResponse,
    VoiceLiveInstanceResponse,
    VoiceLiveInstanceUnassign,
    VoiceLiveInstanceUpdate,
)
from app.services import voice_live_instance_service, voice_live_service
from app.services.avatar_characters import (
    AVATAR_CHARACTERS,
    get_avatar_characters_list,
)
from app.services.voice_live_webrtc import create_webrtc_session_config
from app.services.voice_live_websocket import handle_voice_live_websocket
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/voice-live", tags=["voice-live"])


@router.get("/models", response_model=VoiceLiveModelsResponse, status_code=200)
async def get_voice_live_models(
    user: User = Depends(get_current_user),
) -> VoiceLiveModelsResponse:
    """Return the list of supported Voice Live generative AI models."""
    from app.services.voice_live_models import VOICE_LIVE_MODELS

    models = [
        VoiceLiveModelInfo(
            id=model_id,
            label=info["label"],
            tier=info["tier"],
            description=info["description"],
        )
        for model_id, info in VOICE_LIVE_MODELS.items()
    ]
    return VoiceLiveModelsResponse(models=models)


@router.post("/token", response_model=VoiceLiveTokenResponse, status_code=200)
async def get_voice_live_token(
    hcp_profile_id: str | None = Query(
        None, description="HCP profile ID to source voice/avatar settings"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveTokenResponse:
    """Issue credentials for direct browser-to-Azure Voice Live connection.

    When hcp_profile_id is provided, includes per-HCP voice/avatar settings.
    """
    try:
        return await voice_live_service.get_voice_live_token(db, hcp_profile_id=hcp_profile_id)
    except ValueError as e:
        raise AppException(
            status_code=503,
            code="VOICE_LIVE_NOT_CONFIGURED",
            message=str(e),
        ) from None


@router.get("/status", response_model=VoiceLiveConfigStatus, status_code=200)
async def get_voice_live_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveConfigStatus:
    """Check Voice Live and Avatar availability for the current deployment."""
    return await voice_live_service.get_voice_live_status(db)


@router.post("/webrtc/session", response_model=WebRTCSessionResponse, status_code=200)
async def create_webrtc_session(
    hcp_profile_id: str | None = Query(None, description="HCP profile ID for per-HCP config"),
    vl_instance_id: str | None = Query(None, description="Voice Live instance ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WebRTCSessionResponse:
    """Create a WebRTC session -- returns signaling URL + auth for direct Azure connection.

    The frontend uses the signaling_url to open a WebSocket to Azure for SDP exchange,
    then establishes a direct RTCPeerConnection for bidirectional audio.
    """
    try:
        return await create_webrtc_session_config(db, hcp_profile_id, vl_instance_id)
    except ValueError as e:
        raise AppException(
            status_code=503,
            code="WEBRTC_SESSION_FAILED",
            message=str(e),
        ) from None


@router.get("/avatar-characters", response_model=AvatarCharactersResponse, status_code=200)
async def list_avatar_characters(
    user: User = Depends(get_current_user),
) -> AvatarCharactersResponse:
    """Return the list of available Azure TTS Avatar characters with metadata.

    Includes character names, available styles, CDN thumbnail URLs,
    and is_photo_avatar flag (photo avatars use VASA-1, no style variants).
    """
    chars = get_avatar_characters_list()
    return AvatarCharactersResponse(
        characters=[
            AvatarCharacterInfo(
                id=c["id"],
                display_name=c["display_name"],
                gender=c["gender"],
                is_photo_avatar=c.get("is_photo_avatar", False),
                styles=[AvatarCharacterStyle(**s) for s in c["styles"]],
                default_style=c["default_style"],
                thumbnail_url=c["thumbnail_url"],
            )
            for c in chars
        ]
    )


# ── Voice Live Instance CRUD ────────────────────────────────────────────


@router.post("/instances", response_model=VoiceLiveInstanceResponse, status_code=201)
async def create_voice_live_instance(
    data: VoiceLiveInstanceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveInstanceResponse:
    """Create a new Voice Live configuration instance."""
    instance = await voice_live_instance_service.create_instance(db, data, user.id)
    hcp_count = len(instance.hcp_profiles) if instance.hcp_profiles else 0
    return VoiceLiveInstanceResponse(**{**instance.__dict__, "hcp_count": hcp_count})


@router.get("/instances", response_model=VoiceLiveInstanceListResponse, status_code=200)
async def list_voice_live_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveInstanceListResponse:
    """List all Voice Live configuration instances."""
    items, total = await voice_live_instance_service.list_instances(db, page, page_size)
    resp_items = []
    for inst in items:
        hcp_count = len(inst.hcp_profiles) if inst.hcp_profiles else 0
        resp_items.append(VoiceLiveInstanceResponse(**{**inst.__dict__, "hcp_count": hcp_count}))
    return VoiceLiveInstanceListResponse(items=resp_items, total=total)


@router.post("/instances/unassign", status_code=200)
async def unassign_instance_from_hcp(
    data: VoiceLiveInstanceUnassign,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Remove Voice Live Instance association from an HCP Profile."""
    profile = await voice_live_instance_service.unassign_from_hcp(db, data.hcp_profile_id)
    return {"hcp_profile_id": profile.id, "voice_live_instance_id": None}


@router.get("/instances/{instance_id}", response_model=VoiceLiveInstanceResponse, status_code=200)
async def get_voice_live_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveInstanceResponse:
    """Get a Voice Live configuration instance by ID."""
    instance = await voice_live_instance_service.get_instance(db, instance_id)
    hcp_count = len(instance.hcp_profiles) if instance.hcp_profiles else 0
    return VoiceLiveInstanceResponse(**{**instance.__dict__, "hcp_count": hcp_count})


@router.put("/instances/{instance_id}", response_model=VoiceLiveInstanceResponse, status_code=200)
async def update_voice_live_instance(
    instance_id: str,
    data: VoiceLiveInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveInstanceResponse:
    """Update a Voice Live configuration instance."""
    instance = await voice_live_instance_service.update_instance(db, instance_id, data)
    hcp_count = len(instance.hcp_profiles) if instance.hcp_profiles else 0
    return VoiceLiveInstanceResponse(**{**instance.__dict__, "hcp_count": hcp_count})


@router.delete("/instances/{instance_id}", status_code=204)
async def delete_voice_live_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a Voice Live configuration instance. Fails with 409 if HCPs reference it."""
    await voice_live_instance_service.delete_instance(db, instance_id)


@router.post(
    "/instances/{instance_id}/assign",
    response_model=VoiceLiveInstanceResponse,
    status_code=200,
)
async def assign_instance_to_hcp(
    instance_id: str,
    data: VoiceLiveInstanceAssign,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceLiveInstanceResponse:
    """Assign a Voice Live Instance to an HCP Profile."""
    await voice_live_instance_service.assign_to_hcp(db, instance_id, data.hcp_profile_id)
    instance = await voice_live_instance_service.get_instance(db, instance_id)
    hcp_count = len(instance.hcp_profiles) if instance.hcp_profiles else 0
    return VoiceLiveInstanceResponse(**{**instance.__dict__, "hcp_count": hcp_count})


# ── Avatar ──────────────────────────────────────────────────────────────


@router.get("/avatar-thumbnail/{character_id}", status_code=307)
async def get_avatar_thumbnail(character_id: str) -> Response:
    """Redirect to the CDN thumbnail for the given avatar character.

    No authentication required — thumbnails are non-sensitive static assets.
    """
    from fastapi.responses import RedirectResponse

    char_data = next((c for c in AVATAR_CHARACTERS if c["id"] == character_id), None)
    if char_data:
        return RedirectResponse(
            url=char_data["thumbnail_url"],
            headers={"Cache-Control": "public, max-age=86400"},
        )
    # Unknown character — redirect to a reasonable default
    cdn_base = (
        "https://learn.microsoft.com/en-us/azure/ai-services/"
        "speech-service/text-to-speech-avatar/media"
    )
    return RedirectResponse(
        url=f"{cdn_base}/{character_id}.png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def _authenticate_websocket(
    ws: WebSocket,
    db: AsyncSession,
) -> User | None:
    """Validate JWT token from WebSocket query parameter.

    Browser WebSocket API cannot set HTTP Authorization headers, so the token
    is passed as a query parameter: ws://host/ws?token=xxx

    Returns the authenticated User, or None if authentication fails
    (after sending an error message and closing the connection with 1008).
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.accept()
        await ws.send_text(
            json.dumps(
                {
                    "type": "error",
                    "error": {"message": "Authentication required: missing token query parameter"},
                }
            )
        )
        await ws.close(code=1008, reason="Authentication required")
        return None

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise JWTError("Missing sub claim")
    except JWTError:
        await ws.accept()
        await ws.send_text(
            json.dumps(
                {
                    "type": "error",
                    "error": {"message": "Authentication failed: invalid token"},
                }
            )
        )
        await ws.close(code=1008, reason="Invalid token")
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await ws.accept()
        await ws.send_text(
            json.dumps(
                {
                    "type": "error",
                    "error": {"message": "Authentication failed: user not found or inactive"},
                }
            )
        )
        await ws.close(code=1008, reason="User not found or inactive")
        return None

    return user


@router.websocket("/ws")
async def voice_live_websocket(
    ws: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> None:
    """WebSocket proxy: client ↔ backend ↔ Azure Voice Live.

    Authentication: JWT token must be passed as query parameter `token`.
    Example: ws://host/api/v1/voice-live/ws?token=eyJhbGciOi...

    Protocol:
      1. Client connects to ws://.../api/v1/voice-live/ws?token=<jwt>
      2. Backend validates JWT token (same logic as HTTP endpoints)
      3. Client sends: {"type": "session.update", "session": {"hcp_profile_id": "...", ...}}
      4. Backend connects to Azure Voice Live via Python SDK, sends proxy.connected
      5. Bidirectional message proxy until disconnect
    """
    user = await _authenticate_websocket(ws, db)
    if user is None:
        return  # Authentication failed, connection already closed

    sid = ws.query_params.get("sid", "")
    logger.info("WS connect: user=%s, sid=%s", user.id, sid)
    ws_start = time.monotonic()
    try:
        await handle_voice_live_websocket(ws, db, user.id)
    finally:
        duration = round(time.monotonic() - ws_start, 1)
        logger.info(
            "WS disconnect: user=%s, sid=%s, duration=%.1fs",
            user.id,
            sid,
            duration,
        )
