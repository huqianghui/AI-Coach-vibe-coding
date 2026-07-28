"""Voice Live API request/response schemas."""

from pydantic import BaseModel


class VoiceLiveTokenResponse(BaseModel):
    """Voice Live configuration metadata. Token is always masked (auth handled server-side)."""

    endpoint: str
    token: str
    region: str
    model: str
    avatar_enabled: bool
    avatar_character: str
    voice_name: str
    auth_type: str = "key"  # "key" for API key, "bearer" for STS bearer token
    agent_id: str | None = None
    agent_version: str | None = None
    project_name: str | None = None
    agent_mode_available: bool = False
    agent_warning: str | None = None

    # Per-HCP fields (D-08)
    avatar_style: str = "casual"
    avatar_customized: bool = False
    voice_type: str = "azure-standard"
    voice_temperature: float = 0.9
    voice_custom: bool = False
    turn_detection_type: str = "server_vad"
    noise_suppression: bool = False
    echo_cancellation: bool = False
    eou_detection: bool = False
    recognition_language: str = "auto"


class VoiceLiveModelInfo(BaseModel):
    """Single Voice Live model entry."""

    id: str
    label: str
    tier: str
    description: str


class VoiceLiveModelsResponse(BaseModel):
    """List of supported Voice Live models grouped by tier."""

    models: list[VoiceLiveModelInfo]


class VoiceLiveConfigStatus(BaseModel):
    """Voice Live and Avatar availability status for the current deployment."""

    voice_live_available: bool
    avatar_available: bool
    voice_name: str
    avatar_character: str


class WebRTCSessionResponse(BaseModel):
    """WebRTC session config for direct browser-to-Azure connection.

    Contains the signaling WebSocket URL, bearer auth token, and session configuration
    needed by the frontend to establish a WebRTC peer connection with Azure Voice Live.
    """

    signaling_url: str  # wss://<endpoint>/voice-live/realtime/calls?api-version=...&model=...
    auth_token: str  # Bearer token from STS exchange (short-lived, 10 min)
    auth_type: str  # Always "bearer" for browser WebSocket auth
    model: str  # e.g. "gpt-4o" (empty string for agent mode)
    mode: str  # "agent" | "model"
    session_config: dict  # Voice, turn detection, noise suppression settings
    agent_id: str | None = None
    agent_version: str | None = None
    project_name: str | None = None
    avatar_warning: str | None = None  # Warning when avatar unavailable with WebRTC


class AvatarCharacterStyle(BaseModel):
    """A single style variant of an avatar character."""

    id: str
    display_name: str


class AvatarCharacterInfo(BaseModel):
    """Metadata for one Azure TTS Avatar character."""

    id: str
    display_name: str
    gender: str
    is_photo_avatar: bool = False
    styles: list[AvatarCharacterStyle]
    default_style: str
    thumbnail_url: str


class AvatarCharactersResponse(BaseModel):
    """List of available avatar characters with metadata."""

    characters: list[AvatarCharacterInfo]
