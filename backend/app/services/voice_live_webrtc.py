"""WebRTC session configuration service for Azure Voice Live.

Constructs the signaling WebSocket URL (/voice-live/realtime/calls endpoint)
and exchanges API key for bearer token for browser-safe authentication.
Audio flows directly browser-to-Azure over WebRTC -- backend only brokers auth.
"""

import logging
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.voice_live import WebRTCSessionResponse
from app.services import config_service
from app.services.agents.adapters.azure_voice_live import parse_voice_live_mode
from app.services.voice_live_service import _exchange_api_key_for_bearer_token
from app.utils.azure_endpoints import to_cognitive_services_endpoint
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)

AVATAR_WARNING = "Avatar (digital human) is not supported with WebRTC audio transport in preview."


async def create_webrtc_session_config(
    db: AsyncSession,
    hcp_profile_id: str | None = None,
    vl_instance_id: str | None = None,
) -> WebRTCSessionResponse:
    """Build WebRTC session config: signaling URL + bearer token + session settings.

    Steps:
    1. Load Voice Live config (same as WS proxy logic)
    2. Resolve per-HCP voice/avatar settings if hcp_profile_id provided
    3. Build signaling URL with /voice-live/realtime/calls path
    4. Exchange API key for bearer token via STS
    5. Return everything frontend needs to establish WebRTC connection
    """
    # 1. Load config
    vl_config = await config_service.get_config(db, "azure_voice_live")
    if not vl_config or not vl_config.is_active:
        raise ValueError("Voice Live not configured or inactive")

    api_key = await config_service.get_effective_key(db, "azure_voice_live")
    if not api_key:
        raise ValueError("Voice Live API key not set")

    raw_endpoint = await config_service.get_effective_endpoint(db, "azure_voice_live")
    if not raw_endpoint:
        raise ValueError("Voice Live endpoint not configured")

    # Voice Live WebSocket requires cognitiveservices.azure.com
    effective_endpoint = to_cognitive_services_endpoint(raw_endpoint)

    # Parse agent/model mode from config-level model_or_deployment
    mode_info = parse_voice_live_mode(vl_config.model_or_deployment)
    config_is_agent = mode_info.get("mode") == "agent"

    _default_model = get_settings().voice_live_default_model
    _api_version = get_settings().voice_live_api_version
    voice_live_model = mode_info.get("model", _default_model)

    # Config-level agent/project defaults
    agent_id = mode_info.get("agent_id") if config_is_agent else None
    master = await config_service.get_master_config(db)
    default_project = master.default_project if master else ""
    project_name_val = mode_info.get("project_name") or default_project if config_is_agent else None

    # Default session settings
    voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
    voice_type = "azure-standard"
    turn_detection_type = "server_vad"
    noise_suppression = False
    echo_cancellation = False
    instructions: str | None = None

    # 2. Per-HCP overrides
    if hcp_profile_id:
        from app.services import hcp_profile_service
        from app.services.voice_live_instance_service import resolve_voice_config

        try:
            profile = await hcp_profile_service.get_hcp_profile(db, hcp_profile_id)

            # D-05: auto-resync a classic (asst_*) Foundry Agent to a hosted agent
            # on first WebRTC connection, mirroring the WS-side wiring in
            # voice_live_websocket.py (Plan 29-03). No-op if not asst_-prefixed.
            if (profile.agent_id or "").startswith("asst_"):
                from app.services.agent_sync_service import resync_classic_agent

                await resync_classic_agent(db, profile)

            # D-08: forced agent mode -- a WebRTC voice session for an HCP profile
            # requires a synced hosted agent_id. Reject before any signaling URL
            # or bearer token is built (do not leak a half-configured session).
            if not (profile.agent_id and profile.agent_sync_status == "synced"):
                raise AppException(
                    status_code=409,
                    code="AGENT_SYNC_REQUIRED",
                    message=(
                        f"HCP profile {hcp_profile_id} has no synced Voice Live "
                        "agent. Resync the agent before starting a voice session."
                    ),
                )

            agent_id = profile.agent_id
            project_name_val = default_project

            # Resolve voice config from VoiceLiveInstance or fallback inline fields
            vc = resolve_voice_config(profile)
            voice_name = vc["voice_name"] or "en-US-AvaNeural"
            voice_type = vc["voice_type"] or "azure-standard"
            turn_detection_type = vc["turn_detection_type"] or "server_vad"
            noise_suppression = vc["noise_suppression"]
            echo_cancellation = vc["echo_cancellation"]
            voice_live_model = vc["voice_live_model"] or _default_model
        except AppException:
            # D-08 rejection must propagate untouched -- do NOT let the broad
            # `except Exception` below swallow it and silently fall back to
            # model mode (that would defeat the forced-agent-mode guarantee,
            # the same exception-ordering hazard closed on the WS side in
            # Plan 29-03 / threat T-29-02).
            raise
        except Exception:
            logger.warning(
                "Failed to load HCP profile %s for WebRTC session, using defaults",
                hcp_profile_id,
                exc_info=True,
            )

    # Determine final mode
    is_agent = bool(agent_id)

    # 3. Build signaling URL
    parsed = urlparse(effective_endpoint)
    endpoint_host = parsed.hostname or parsed.netloc

    if is_agent:
        signaling_url = (
            f"wss://{endpoint_host}/voice-live/realtime/calls"
            f"?api-version={_api_version}"
            f"&agent_id={agent_id}"
            f"&project_id={project_name_val or ''}"
        )
    else:
        signaling_url = (
            f"wss://{endpoint_host}/voice-live/realtime/calls"
            f"?api-version={_api_version}"
            f"&model={voice_live_model}"
        )

    # 4. Exchange API key for bearer token via STS
    bearer_token = await _exchange_api_key_for_bearer_token(effective_endpoint, api_key)

    # 5. Build session_config for frontend session.update
    session_config: dict = {
        "voice": {
            "name": voice_name,
            "type": voice_type,
        },
        "turn_detection": {
            "type": turn_detection_type,
        },
        "input_audio_noise_reduction": noise_suppression,
        "input_audio_echo_cancellation": echo_cancellation,
    }
    if instructions:
        session_config["instructions"] = instructions

    logger.info(
        "WebRTC session created: mode=%s, model=%s, agent=%s, host=%s",
        "agent" if is_agent else "model",
        voice_live_model if not is_agent else "",
        agent_id or "none",
        endpoint_host,
    )

    return WebRTCSessionResponse(
        signaling_url=signaling_url,
        auth_token=bearer_token,
        auth_type="bearer",
        model=voice_live_model if not is_agent else "",
        mode="agent" if is_agent else "model",
        session_config=session_config,
        agent_id=agent_id,
        project_name=project_name_val,
        avatar_warning=AVATAR_WARNING,
    )
