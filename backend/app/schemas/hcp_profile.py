"""HCP Profile request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.voice_live_instance import VoiceLiveInstanceSummary


class HcpProfileCreate(BaseModel):
    """Create a new HCP profile."""

    name: str
    specialty: str
    created_by: str = ""
    hospital: str = ""
    title: str = ""
    avatar_url: str = ""
    personality_type: Literal["friendly", "skeptical", "busy", "analytical", "cautious"] = (
        "friendly"
    )
    emotional_state: int = Field(default=50, ge=0, le=100)
    communication_style: int = Field(default=50, ge=0, le=100)
    expertise_areas: list[str] = []
    prescribing_habits: str = ""
    concerns: str = ""
    objections: list[str] = []
    probe_topics: list[str] = []
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    is_active: bool = True

    # Voice Live Instance reference (required, D-13 -- every HCP must reference exactly
    # one VoiceLiveInstance for its full voice+avatar configuration)
    voice_live_instance_id: str = Field(..., min_length=1)

    agent_instructions_override: str = ""


class HcpProfileUpdate(BaseModel):
    """Update an existing HCP profile. All fields optional for partial updates."""

    name: str | None = None
    specialty: str | None = None
    hospital: str | None = None
    title: str | None = None
    avatar_url: str | None = None
    personality_type: Literal["friendly", "skeptical", "busy", "analytical", "cautious"] | None = (
        None
    )
    emotional_state: int | None = Field(default=None, ge=0, le=100)
    communication_style: int | None = Field(default=None, ge=0, le=100)
    expertise_areas: list[str] | None = None
    prescribing_habits: str | None = None
    concerns: str | None = None
    objections: list[str] | None = None
    probe_topics: list[str] | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    is_active: bool | None = None

    # Voice Live Instance reference. Optional at the type level so partial updates can
    # omit it and leave the existing value untouched -- but if the caller DOES send it,
    # empty string is rejected here. The "cannot be cleared" invariant (D-13) is enforced
    # in the service layer since the schema alone cannot know the pre-update DB value.
    voice_live_instance_id: str | None = Field(default=None, min_length=1)
    agent_instructions_override: str | None = None


class HcpProfileResponse(BaseModel):
    """HCP profile response with all fields."""

    id: str
    name: str
    specialty: str
    hospital: str
    title: str
    avatar_url: str
    personality_type: str
    emotional_state: int
    communication_style: int
    expertise_areas: str  # JSON string from DB
    prescribing_habits: str
    concerns: str
    objections: str  # JSON string from DB
    probe_topics: str  # JSON string from DB
    difficulty: str
    is_active: bool
    agent_id: str = ""
    agent_version: str = ""
    agent_sync_status: str = "none"
    agent_sync_error: str = ""

    # Voice Live Instance reference
    voice_live_instance_id: str | None = None
    voice_live_instance: VoiceLiveInstanceSummary | None = None

    agent_instructions_override: str = ""

    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HcpProfileListResponse(BaseModel):
    """Paginated list of HCP profiles."""

    items: list[HcpProfileResponse]
    total: int
