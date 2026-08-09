"""Voice Live Instance request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VoiceLiveInstanceCreate(BaseModel):
    """Create a new Voice Live configuration instance."""

    name: str
    description: str = ""

    # Voice Live core
    voice_live_model: str = "gpt-4o"
    enabled: bool = True

    # Voice settings
    voice_name: str = "en-US-AvaNeural"
    voice_type: str = "azure-standard"
    voice_temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    voice_custom: bool = False

    # Avatar settings
    avatar_character: str = "lori"
    avatar_style: str = "casual"
    avatar_customized: bool = False

    # Conversation parameters
    turn_detection_type: str = "server_vad"
    noise_suppression: bool = False
    echo_cancellation: bool = False
    eou_detection: bool = False
    recognition_language: str = "auto"

    # Response settings (AI Foundry Image #8)
    response_temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    proactive_engagement: bool = True

    # Speech input (AI Foundry Image #9)
    auto_detect_language: bool = True

    # Speech output (AI Foundry Image #10)
    playback_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    custom_lexicon_enabled: bool = False
    custom_lexicon_url: str = ""

    # Avatar toggle (AI Foundry Image #11)
    avatar_enabled: bool = True

    # Model instruction (VL Instance is a model/API, not an agent)
    model_instruction: str = ""


class VoiceLiveInstanceUpdate(BaseModel):
    """Update a Voice Live configuration instance. All fields optional."""

    name: str | None = None
    description: str | None = None
    voice_live_model: str | None = None
    enabled: bool | None = None
    voice_name: str | None = None
    voice_type: str | None = None
    voice_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    voice_custom: bool | None = None
    avatar_character: str | None = None
    avatar_style: str | None = None
    avatar_customized: bool | None = None
    turn_detection_type: str | None = None
    noise_suppression: bool | None = None
    echo_cancellation: bool | None = None
    eou_detection: bool | None = None
    recognition_language: str | None = None
    response_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    proactive_engagement: bool | None = None
    auto_detect_language: bool | None = None
    playback_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    custom_lexicon_enabled: bool | None = None
    custom_lexicon_url: str | None = None
    avatar_enabled: bool | None = None
    model_instruction: str | None = None


class VoiceLiveInstanceResponse(BaseModel):
    """Full Voice Live Instance response."""

    id: str
    name: str
    description: str
    voice_live_model: str
    enabled: bool
    voice_name: str
    voice_type: str
    voice_temperature: float
    voice_custom: bool
    avatar_character: str
    avatar_style: str
    avatar_customized: bool
    turn_detection_type: str
    noise_suppression: bool
    echo_cancellation: bool
    eou_detection: bool
    recognition_language: str
    response_temperature: float
    proactive_engagement: bool
    auto_detect_language: bool
    playback_speed: float
    custom_lexicon_enabled: bool
    custom_lexicon_url: str
    avatar_enabled: bool
    model_instruction: str
    hcp_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoiceLiveInstanceSummary(BaseModel):
    """Compact summary for HCP profile / scenario embedding.

    Deliberately omits aggregate fields (e.g. ``hcp_count``) that require a
    separate query to compute -- this schema validates directly from the raw
    ``VoiceLiveInstance`` ORM object via attribute lookup (``from_attributes``)
    when nested under ``hcp_profile.voice_live_instance``, so any field here
    must be a plain column on the model or it will silently resolve to its
    Pydantic default instead of erroring (Phase 30 review, WR-01).
    """

    id: str
    name: str
    voice_live_model: str
    enabled: bool
    voice_name: str
    avatar_character: str
    avatar_style: str
    avatar_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class VoiceLiveInstanceListResponse(BaseModel):
    """Paginated list of Voice Live instances."""

    items: list[VoiceLiveInstanceResponse]
    total: int


class VoiceLiveInstanceAssign(BaseModel):
    """Assign a Voice Live Instance to an HCP Profile."""

    hcp_profile_id: str


class VoiceLiveInstanceUnassign(BaseModel):
    """Unassign Voice Live Instance from an HCP Profile."""

    hcp_profile_id: str
