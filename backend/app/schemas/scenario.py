"""Scenario request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModeratorRemarks(BaseModel):
    """Localized moderator remarks for conference flow phases."""

    zh: str = ""
    en: str = ""


class ConferencePromptConfig(BaseModel):
    """Configurable conference orchestration prompts."""

    speaker_order_policy: str = ""
    audience_prompt_template: str = ""
    moderator_remarks: dict[str, ModeratorRemarks] = Field(default_factory=dict)


class ScenarioCreate(BaseModel):
    """Create a new scenario."""

    name: str
    hcp_profile_id: str
    rubric_id: str
    skill_id: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    mode: str = "f2f"
    difficulty: str = "medium"
    key_messages: list[str] = Field(default_factory=list)
    conference_prompt_config: ConferencePromptConfig | None = None
    pass_threshold: int = 70


class ScenarioUpdate(BaseModel):
    """Update an existing scenario. All fields optional for partial updates."""

    name: str | None = None
    hcp_profile_id: str | None = None
    rubric_id: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    mode: str | None = None
    difficulty: str | None = None
    key_messages: list[str] | None = None
    conference_prompt_config: ConferencePromptConfig | None = None
    skill_id: str | None = None
    pass_threshold: int | None = None


class HcpProfileSummary(BaseModel):
    """Lightweight HCP profile embedded in scenario response (avatar metadata)."""

    id: str
    name: str
    specialty: str
    avatar_character: str = "lori"
    avatar_style: str = "casual"
    voice_live_enabled: bool = False
    voice_live_instance_id: str | None = None
    avatar_enabled: bool = False

    model_config = ConfigDict(from_attributes=True)


class ScenarioResponse(BaseModel):
    """Scenario response with all fields."""

    id: str
    name: str
    description: str
    tags: str  # JSON string from DB
    mode: str
    difficulty: str
    status: str
    hcp_profile_id: str
    hcp_profile: HcpProfileSummary | None = None
    key_messages: str  # JSON string from DB
    conference_prompt_config: str
    conference_prompt_version: int = 1
    skill_id: str
    skill_version_id: str | None = None
    rubric_id: str
    pass_threshold: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
